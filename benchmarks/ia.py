"""Ejecuta los cuatro contratos sin inicializar Django."""
import argparse
import csv
import json
import os
import re
from datetime import date
from pathlib import Path
from time import perf_counter, sleep
from urllib.error import HTTPError, URLError

from dotenv import dotenv_values

from apps.external_services.ai_errors import AnalisisNoDisponible
from apps.external_services.api_ia import APIBibliografia, APIJSON, APIPreguntas, APISuficiencia, APIValoracion
from apps.external_services.clientes_ia import MODELOS_GOOGLE_CANDIDATOS, bytes_contexto
from benchmarks.casos_ia import CASOS
from benchmarks.clientes_ia import (
    PROVEEDORES, PROVEEDORES_OPERATIVOS, TYPHOON_MODELO, ClienteBenchmark, autorizar, validar_endpoint_openrouter,
)
from benchmarks.cuotas_google import PresupuestoGoogle


ADAPTADORES = {
    "bibliografia": APIBibliografia, "preguntas": APIPreguntas,
    "suficiencia": APISuficiencia, "valoracion": APIValoracion,
}
TOKENS = ("tokens_entrada", "tokens_salida", "tokens_totales")
ENV_PROYECTO = Path(__file__).resolve().parents[1] / ".env"


def leer_variable(variables, *nombres, defecto=""):
    for nombre in nombres:
        valor = variables.get(nombre)
        if valor and valor.strip():
            return valor.strip()
    return defecto


def detalle_http(error):
    """Resume indicios conocidos sin copiar texto, encabezados ni datos remotos."""
    if error.code not in (401, 403):
        return None
    try:
        cuerpo = error.read(8192).decode("utf-8", errors="replace").casefold()
    except (OSError, AttributeError, ValueError):
        return None
    for fragmentos, detalle in (
        (("invalid_api_key", "invalid api key"), "El servidor indica que la clave es inválida."),
        (("model_permission", "model is not allowed", "does not have access to model",
          "access to this model", "model is restricted"), "El servidor indica una restricción de acceso al modelo."),
        (("unsupported_country", "unsupported country", "region is not supported",
          "country, region, or territory"), "El servidor indica una restricción regional."),
        (("proxy", "network policy", "web filter"), "La respuesta contiene indicios de un proxy o filtro de red."),
    ):
        if any(fragmento in cuerpo for fragmento in fragmentos):
            return detalle
    return "El cuerpo no contiene un motivo reconocido que se pueda exportar de forma segura."


def ids_validos(caso, datos):
    if caso.operacion == "preguntas":
        return None
    if not isinstance(datos, dict):
        return False
    if caso.operacion == "bibliografia":
        sugerencias = datos.get("sugerencias")
        if not isinstance(sugerencias, list) or any(not isinstance(x, dict) for x in sugerencias):
            return False
        ids = [x.get("publicacion_id") for x in sugerencias]
        permitidos = [x["id"] for x in caso.entrada["publicaciones"]]
        return all(type(x) is int and x in permitidos for x in ids) and len(ids) == len(set(ids))
    ids = datos.get("referencias")
    permitidos = [x["id"] for x in caso.entrada["fuentes"]]
    return isinstance(ids, list) and all(isinstance(x, str) and x in permitidos for x in ids)


def evaluar(caso, datos):
    esperado = caso.esperado
    if caso.operacion == "bibliografia":
        ids = {x["publicacion_id"] for x in datos["sugerencias"]}
        return ids == {x["publicacion_id"] for x in esperado["sugerencias"]}
    if caso.operacion == "valoracion":
        return (datos["valor_preliminar"] == esperado["valor_preliminar"]
                and set(datos["referencias"]) == set(esperado["referencias"]))
    if caso.operacion == "suficiencia":
        if datos["estado"] != esperado["estado"]:
            return False
        if esperado["estado"] == "SUFICIENTE" and set(datos["referencias"]) != set(esperado["referencias"]):
            return False
    preguntas = datos["preguntas"]
    return len(preguntas) == len(caso.temas) and all(
        any(termino in pregunta.casefold() for termino in alternativas)
        for pregunta, alternativas in zip(preguntas, caso.temas)
    )


def transporte_mock(proveedor, caso, modelo=None):
    def responder(url, carga, clave, timeout):
        texto = json.dumps(caso.esperado, ensure_ascii=False)
        if proveedor == "cohere":
            return {"message": {"content": [{"type": "text", "text": texto}]}}
        if proveedor == "gemini" and modelo in MODELOS_GOOGLE_CANDIDATOS:
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": texto}]}}]}
        return {"choices": [{"message": {"content": texto}}]}
    return responder


def configurar(proveedores, modo, autorizaciones, variables=None, modelo_explicito=None):
    if variables is None:
        variables = os.environ
    configuraciones = {}
    for proveedor in proveedores:
        nombre = proveedor.upper()
        prefijo = "GUIOS_AI_" + nombre
        if modo == "mock":
            modelo_mock = TYPHOON_MODELO if proveedor == "typhoon" else f"mock-{proveedor}"
            configuraciones[proveedor] = (modelo_explicito or modelo_mock, "mock", 15, "mock", "mock")
            continue
        modelo = modelo_explicito or leer_variable(variables, prefijo + "_MODEL", nombre + "_MODEL")
        nombres_clave = [prefijo + "_API_KEY"]
        if proveedor == "cloudflare":
            nombres_clave.append(prefijo + "_API_TOKEN")
        clave = leer_variable(variables, *nombres_clave, prefijo + "_KEY", nombre + "_API_KEY")
        if not clave or not re.fullmatch(r"[@a-zA-Z0-9][a-zA-Z0-9_./:+@-]{0,149}", modelo):
            raise ValueError(f"Configure {prefijo}_MODEL y {prefijo}_API_KEY.")
        endpoint = autorizar(proveedor, modelo, autorizaciones, date.today(), benchmark=True)
        cuenta = ""
        if proveedor == "cloudflare":
            cuenta = leer_variable(variables, prefijo + "_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID")
        if proveedor == "cloudflare" and not re.fullmatch(r"[a-fA-F0-9]{32}", cuenta):
            raise ValueError("Configure GUIOS_AI_CLOUDFLARE_ACCOUNT_ID.")
        configuraciones[proveedor] = (modelo, clave, int(leer_variable(
                                      variables, "GUIOS_AI_TIMEOUT", defecto="15")),
                                      cuenta, endpoint)
    return configuraciones


def ejecutar(configuraciones, modo, transporte=None, casos=CASOS, presupuesto_google=None):
    if any((seleccion[0] if isinstance(seleccion, tuple) else seleccion) == 'typhoon'
           for seleccion in configuraciones):
        if any(not any(caso is sintetico for sintetico in CASOS) for caso in casos):
            raise ValueError('Typhoon solo admite los casos sintéticos incluidos en el benchmark.')
    filas = []
    bloqueos = {}
    for seleccion, configuracion in configuraciones.items():
        proveedor = seleccion[0] if isinstance(seleccion, tuple) else seleccion
        modelo = configuracion[0]
        bloqueo_http = bloqueos.get(proveedor)
        presupuesto = presupuesto_google if proveedor == "gemini" else None
        siguiente_typhoon = 0
        for caso in casos:
            fila = dict(modo=modo, proveedor=proveedor, modelo=modelo,
                        operacion=caso.operacion, caso=caso.id, latencia_ms=None,
                        json_valido=None, contrato_valido=None, referencias_validas=None,
                        calidad_ok=None, http_status=None, error=None, detalle_http=None,
                        espera_cuota_ms=None, tokens_reservados=None)
            fila.update(dict.fromkeys(TOKENS))
            filas.append(fila)
            if bloqueo_http:
                fila["error"] = f"omitido_por_{bloqueo_http}"
                continue
            envio = transporte or (transporte_mock(proveedor, caso, modelo) if modo == "mock" else None)
            opciones = {"transporte": envio} if envio else {}
            cliente = ClienteBenchmark(proveedor, *configuracion, **opciones)
            reserva = None
            if presupuesto:
                carga = APIJSON.preparar_carga(modelo, caso.entrada, *ADAPTADORES[caso.operacion].contrato(caso.entrada))
                reserva = bytes_contexto(carga) + presupuesto.margen_entrada + presupuesto.salida
                espera = perf_counter()
                if not presupuesto.admitir(reserva):
                    fila["error"] = "omitido_por_presupuesto"
                    continue
                fila["espera_cuota_ms"] = round((perf_counter() - espera) * 1000, 3)
                fila["tokens_reservados"] = reserva
                cliente.max_tokens_salida = presupuesto.salida
                cliente.margen_tokens_entrada = presupuesto.margen_entrada
                cliente.tokens_reservados = reserva
            if proveedor == "typhoon" and modo == "real":
                espera = max(0, siguiente_typhoon - perf_counter())
                if espera:
                    sleep(espera)
                fila["espera_cuota_ms"] = round(espera * 1000, 3)
                siguiente_typhoon = perf_counter() + 1
            inicio = perf_counter()
            try:
                ADAPTADORES[caso.operacion](cliente)(caso.entrada)
            except AnalisisNoDisponible as error:
                causa = error.__cause__
                if isinstance(causa, HTTPError):
                    fila["http_status"] = causa.code
                    if causa.code in (401, 403, 429):
                        bloqueo_http = causa.code
                    fila["error"] = "cuota" if causa.code == 429 else "http"
                    fila["detalle_http"] = detalle_http(causa)
                    causa.close()
                elif isinstance(causa, (URLError, OSError)):
                    fila["error"] = "transporte"
                    tunel = re.search(r"Tunnel connection failed: (401|403)\b",
                                      str(getattr(causa, "reason", causa)), re.IGNORECASE)
                    if tunel:
                        bloqueo_http = int(tunel.group(1))
                        fila["http_status"] = bloqueo_http
                        fila["detalle_http"] = "El proxy rechazó el túnel HTTPS."
                    elif presupuesto or proveedor == "typhoon":
                        bloqueo_http = "transporte_incierto"
                else:
                    fila["error"] = "respuesta_invalida"
            finally:
                fila["latencia_ms"] = round((perf_counter() - inicio) * 1000, 3)
                if presupuesto:
                    presupuesto.cerrar(reserva)
            if (presupuesto or proveedor == "typhoon") and fila["http_status"] in (408, 502, 504):
                bloqueo_http = "transporte_incierto"
            if bloqueo_http:
                bloqueos[proveedor] = bloqueo_http
            fila["json_valido"] = cliente.json_valido
            fila["contrato_valido"] = fila["error"] is None
            if cliente.json_valido:
                fila["referencias_validas"] = ids_validos(caso, cliente.resultado_json)
            if fila["contrato_valido"]:
                fila["calidad_ok"] = evaluar(caso, cliente.resultado_json)
            for campo in TOKENS:
                valor = cliente.uso.get(campo)
                if type(valor) is int and valor >= 0:
                    fila[campo] = valor
    return filas


def exportar(filas, destino):
    destino.mkdir(parents=True, exist_ok=True)
    with (destino / "resultados.json").open("x", encoding="utf-8") as archivo:
        json.dump(filas, archivo, ensure_ascii=False, indent=2)
    with (destino / "resultados.csv").open("x", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=list(filas[0]))
        escritor.writeheader()
        for fila in filas:
            escritor.writerow({
                campo: "'" + valor if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@")) else valor
                for campo, valor in fila.items()
            })


def _seleccionar_modelo(valor):
    proveedor, separador, modelo = valor.partition("=")
    if (not separador or proveedor not in PROVEEDORES
            or not re.fullmatch(r"[@a-zA-Z0-9][a-zA-Z0-9_./:+@-]{0,149}", modelo)):
        raise argparse.ArgumentTypeError("Indique proveedor=identificador del modelo.")
    return proveedor, modelo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modo", choices=("mock", "real"), default="mock")
    seleccion = parser.add_mutually_exclusive_group()
    seleccion.add_argument("--proveedores", nargs="+", choices=tuple(PROVEEDORES),
                          default=list(PROVEEDORES_OPERATIVOS))
    seleccion.add_argument("--modelo", action="append", type=_seleccionar_modelo,
                          help="Modelo exacto proveedor=ID. Se puede repetir sin editar .env.")
    parser.add_argument("--presupuesto-google", type=int,
                        help="Solicitudes aún disponibles verificadas por el operador para el benchmark aislado (1–30).")
    parser.add_argument("--autorizacion", type=Path)
    parser.add_argument("--casos", nargs="+", choices=[caso.id for caso in CASOS],
                        help="Ejecutar únicamente los casos indicados.")
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    try:
        if any((args.salida / nombre).exists() for nombre in ("resultados.json", "resultados.csv")):
            parser.error("La carpeta de salida ya contiene resultados.")
        autorizaciones = []
        variables = {}
        if args.modo == "real":
            if not args.autorizacion:
                parser.error("El modo real requiere --autorizacion con una revisión gratuita vigente.")
            autorizaciones = json.loads(args.autorizacion.read_text(encoding="utf-8-sig"))
            if not isinstance(autorizaciones, list) or any(not isinstance(x, dict) for x in autorizaciones):
                parser.error("El archivo de autorización debe contener una lista de objetos.")
            variables = {**dotenv_values(ENV_PROYECTO, encoding="utf-8-sig", interpolate=False),
                         **os.environ}
        configuraciones = {}
        solicitados = args.modelo or [(proveedor, None) for proveedor in args.proveedores]
        for proveedor, modelo in dict.fromkeys(solicitados):
            try:
                configuracion = configurar([proveedor], args.modo, autorizaciones, variables, modelo)[proveedor]
                if args.modo == "real" and proveedor == "openrouter":
                    try:
                        validar_endpoint_openrouter(configuracion[0], configuracion[4], configuracion[2])
                    except ValueError:
                        print("openrouter: omitido porque el endpoint exacto no pudo verificarse a precio cero.")
                        continue
                configuraciones[(proveedor, configuracion[0])] = configuracion
            except (ValueError, TypeError, AttributeError):
                if args.modelo:
                    parser.error(f"Revise la configuración y autorización exacta de los modelos solicitados para {proveedor}.")
                print(f"{proveedor}: omitido por configuración o autorización inválida.")
        if not configuraciones:
            parser.error("Ningún proveedor está autorizado y configurado.")
        casos = tuple(caso for caso in CASOS if not args.casos or caso.id in args.casos)
        google = [modelo for proveedor, modelo in configuraciones if proveedor == "gemini"]
        control_google = args.modo == "real" and (
            len(google) > 1 or any(modelo in MODELOS_GOOGLE_CANDIDATOS for modelo in google)
            or (bool(google) and args.presupuesto_google is not None)
        )
        if control_google and not len(google) * len(casos) <= (args.presupuesto_google or 0) <= 30:
            parser.error("Indique --presupuesto-google con el saldo verificado (hasta 30) que cubra todos los casos Google.")
        presupuesto = PresupuestoGoogle(args.presupuesto_google) if control_google else None
        args.salida.mkdir(parents=True, exist_ok=True)
        filas = ejecutar(configuraciones, args.modo, casos=casos, presupuesto_google=presupuesto)
        exportar(filas, args.salida)
    except (ValueError, OSError, TypeError, AttributeError):
        parser.error("Configuración, autorización o salida inválida. Revise los parámetros y el archivo de autorización.")
    exitos = sum(fila["contrato_valido"] is True for fila in filas)
    print(f"{exitos}/{len(filas)} contratos válidos. Resultados exportados a JSON y CSV.")


if __name__ == "__main__":
    main()
