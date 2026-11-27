"""Selección secuencial de proveedores externos autorizados para cada operación."""
import json
import re
from dataclasses import dataclass, field
from datetime import date
import hmac
from hashlib import sha256
from pathlib import Path
from threading import local
from time import monotonic, sleep
from urllib.error import HTTPError

from django.conf import settings
from django.db import DatabaseError, connection

from apps.external_services.ai_errors import AnalisisNoDisponible, ErrorProveedor, Motivo
from apps.external_services.api_ia import APIBibliografia, APIJSON, APIPreguntas, APISuficiencia, APIValoracion
from apps.external_services.clientes_ia import PROVEEDORES, ClienteProveedor, autorizar, bytes_contexto, preparar_peticion
from apps.external_services.planificador_ia import (
    MENSAJE_INCIERTA, PlanificadorIA, TareaIncierta, leer_modelos_adicionales,
    leer_perfiles, leer_politicas, politicas_compartidas,
)


_ADAPTADORES = {
    'bibliografia': APIBibliografia,
    'preguntas': APIPreguntas,
    'suficiencia': APISuficiencia,
    'valoracion': APIValoracion,
}



@dataclass(frozen=True)
class ProveedorConfigurado:
    nombre: str
    modelo: str
    clave: str = field(repr=False)
    operaciones: frozenset
    unidad_cuota: str
    cuenta: str = field(repr=False)
    endpoint: str
    adicional: bool = False

    @property
    def identificador_config(self):
        return f'{self.nombre}/{self.modelo}'

    @property
    def credencial(self):
        return hmac.new(settings.SECRET_KEY.encode(), f'{self.nombre}:{self.clave}'.encode(), sha256).hexdigest()


def _leer_proveedores():
    ruta = getattr(settings, 'GUIOS_AI_AUTORIZACION_GRATUITA', '')
    if not ruta:
        return []
    try:
        entradas = json.loads(Path(ruta).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return []
    if not isinstance(entradas, list) or any(not isinstance(entrada, dict) for entrada in entradas):
        return []

    proveedores = []
    perfiles = leer_perfiles()
    adicionales = leer_modelos_adicionales()
    for nombre in PROVEEDORES:
        prefijo = f'GUIOS_AI_{nombre.upper()}'
        clave = getattr(settings, f'{prefijo}_API_KEY', '').strip()
        principal = getattr(settings, f'{prefijo}_MODEL', '').strip()
        if not clave:
            continue
        cuenta = getattr(settings, f'{prefijo}_ACCOUNT_ID', '').strip()
        if nombre == 'cloudflare' and not re.fullmatch(r'[a-fA-F0-9]{32}', cuenta):
            continue
        unidad = getattr(settings, f'{prefijo}_UNIDAD_CUOTA', '').strip() or nombre
        if len(unidad) > 64:
            continue
        modelos_extra = adicionales.get(nombre)
        modelos = dict(modelos_extra) if isinstance(modelos_extra, dict) else {}
        modelos.pop(principal, None)
        if principal:
            modelos = {principal: getattr(settings, f'{prefijo}_OPERACIONES', ''), **modelos}
        for modelo, habilitadas in modelos.items():
            if (not isinstance(habilitadas, str)
                    or not re.fullmatch(r'[@a-zA-Z0-9][a-zA-Z0-9_./:+@-]{0,91}', modelo)):
                continue
            operaciones = frozenset(habilitadas.replace(',', ' ').split())
            perfil = perfiles.get(f'{nombre}/{modelo}')
            if not operaciones <= _ADAPTADORES.keys() or not isinstance(perfil, dict):
                continue
            operaciones = frozenset(
                op for op in operaciones if isinstance(perfil.get(op), dict)
                and perfil[op].get('validado') is True
            )
            if not operaciones:
                continue
            try:
                endpoint = autorizar(nombre, modelo, entradas, date.today())
            except (ValueError, TypeError, AttributeError):
                continue
            proveedores.append(ProveedorConfigurado(nombre, modelo, clave, operaciones, unidad, cuenta, endpoint,
                                                    adicional=modelo != principal))
    return proveedores


def leer_admision():
    politicas = leer_politicas()
    por_modelo = leer_politicas('GUIOS_AI_POLITICAS_MODELO')
    proveedores = []
    for proveedor in _leer_proveedores():
        proyecto = politicas.get(proveedor.unidad_cuota)
        modelo = por_modelo.get(proveedor.identificador_config)
        if not proyecto or (proveedor.adicional and not modelo):
            continue
        if proveedor.nombre == 'cloudflare' and 'unidades_diarias' not in proyecto.ventanas:
            continue
        if modelo and 'unidades_diarias' in proyecto.ventanas and 'unidades_diarias' not in modelo.ventanas:
            # Un modelo no puede descontar cero en una unidad con cobro por consumo.
            continue
        proveedores.append(proveedor)
    return proveedores, politicas_compartidas(politicas, proveedores, por_modelo), por_modelo


def modelo_activo(tipo=None):
    proveedores, _, _ = leer_admision()
    return ' + '.join(dict.fromkeys(p.nombre.capitalize() for p in proveedores
                                   if tipo is None or tipo in p.operaciones))


def configurado():
    return bool(modelo_activo())


def _clave_tarea(tipo, entrada, ambito):
    contrato = json.dumps([1, tipo, ambito, entrada], sort_keys=True, ensure_ascii=False)
    return hmac.new(settings.SECRET_KEY.encode(), contrato.encode(), sha256).hexdigest()


def _tokens(uso):
    total = uso.get('tokens_totales')
    if type(total) is int and 0 <= total <= 2**63 - 1:
        return total
    entrada, salida = uso.get('tokens_entrada'), uso.get('tokens_salida')
    if all(type(v) is int and 0 <= v <= (2**63 - 1) // 2 for v in (entrada, salida)):
        return entrada + salida
    return None


def _neurons_observados(uso, politica, total):
    if not politica.neurons_por_millon_entrada or total is None:
        return 0
    entrada, salida = uso.get('tokens_entrada'), uso.get('tokens_salida')
    if all(type(v) is int and 0 <= v <= total for v in (entrada, salida)) and entrada + salida == total:
        return politica.calcular_neurons(entrada, salida)
    # Sin desglose, aplicar la tasa mayor y cubrir el redondeo de ambas categorías.
    tasa = max(politica.neurons_por_millon_entrada, politica.neurons_por_millon_salida)
    return (total * tasa + 999_999) // 1_000_000 + bool(total)


def _consumo_confirmado(uso, politica):
    total = uso.get('tokens_totales')
    entrada, salida = uso.get('tokens_entrada'), uso.get('tokens_salida')
    if (not politica.reconciliar_uso or type(total) is not int or not 0 < total <= 2**63 - 1
            or not all(type(n) is int and 0 < n <= total for n in (entrada, salida))
            or entrada + salida > total):
        return None, None
    unidades = None
    if politica.neurons_por_millon_entrada:
        if entrada + salida != total:
            return None, None
        unidades = politica.calcular_neurons(entrada, salida)
    return total, unidades


def medir_peticion(tipo, entrada, proveedor, modelo, salida, endpoint=''):
    carga = APIJSON.preparar_carga(modelo, entrada, *_ADAPTADORES[tipo].contrato(entrada))
    contexto = bytes_contexto(carga)
    preparar_peticion(proveedor, carga, endpoint, salida)
    return len(json.dumps(carga, ensure_ascii=False).encode('utf-8')), contexto


class AdministradorProveedores:
    def consultar(self, tipo, entrada, ambito=None, actor_id=None):
        if connection.in_atomic_block:
            raise AnalisisNoDisponible('El análisis de IA requiere ejecutarse fuera de una transacción.')
        proveedores, politicas, politicas_modelo = leer_admision()
        perfiles = leer_perfiles()
        candidatos = [p for p in proveedores if tipo in p.operaciones]
        clave = _clave_tarea(tipo, entrada, ambito)
        try:
            propietario, cache = PlanificadorIA.tomar(clave, actor_id)
            if cache is not None:
                return cache
            try:
                return self._despachar(clave, propietario, tipo, entrada, candidatos,
                                       politicas, politicas_modelo, perfiles, actor_id)
            finally:
                PlanificadorIA.liberar(clave, propietario)
        except DatabaseError:
            raise AnalisisNoDisponible('La coordinación de IA no está disponible. Puede continuar manualmente.') from None

    @staticmethod
    def _despachar(clave, propietario, tipo, entrada, candidatos, politicas, politicas_modelo, perfiles, actor_id):
        costes = {}
        bytes_entrada = None
        for proveedor in candidatos:
            proyecto = politicas[proveedor.unidad_cuota]
            politica = politicas_modelo.get(proveedor.identificador_config, proyecto)
            if politica.margen_tokens_entrada is not None:
                if bytes_entrada is None:
                    carga = APIJSON.preparar_carga(proveedor.modelo, entrada, *_ADAPTADORES[tipo].contrato(entrada))
                    bytes_entrada = bytes_contexto(carga)
                politica = politica.para_peticion(bytes_entrada)
            if (politica is not None and politica.cabe_en(proyecto)
                    and politica.cabe_en(politicas_modelo.get(proveedor.identificador_config, proyecto))):
                costes[proveedor] = politica
        candidatos = list(costes)
        fallback = False
        inicio_espera = monotonic()
        while candidatos:
            espera = monotonic() - inicio_espera
            reserva, puede_esperar = PlanificadorIA.reservar(
                clave, propietario, tipo, candidatos, politicas, perfiles, round(espera * 1000), fallback,
                costes, politicas_modelo,
            )
            if reserva is None:
                restante = settings.GUIOS_AI_ESPERA_SEGUNDOS - espera
                if not puede_esperar or restante <= 0:
                    break
                sleep(min(0.2, restante))
                continue
            proveedor, politica, intento = reserva
            candidatos.remove(proveedor)
            inicio = monotonic()
            resultado = error = None
            terminada = False
            cliente = None
            try:
                cliente = ClienteProveedor(
                    proveedor.nombre, proveedor.modelo, proveedor.clave, settings.GUIOS_AI_TIMEOUT,
                    proveedor.cuenta, proveedor.endpoint,
                )
                cliente.max_tokens_salida = politica.max_tokens_salida
                cliente.tokens_reservados = politica.tokens_por_intento
                cliente.margen_tokens_entrada = politica.margen_tokens_entrada
                resultado = _ADAPTADORES[tipo](cliente)(entrada)
                terminada = True
            except ErrorProveedor as exc:
                error = exc
                terminada = exc.motivo not in (Motivo.TIMEOUT, Motivo.RED) and exc.estado_http not in (408, 502, 504)
                if isinstance(exc.__cause__, HTTPError):
                    exc.__cause__.close()
            except AnalisisNoDisponible:
                # Las validaciones de entrada y de configuracion rechazan antes del envio.
                error = ErrorProveedor(Motivo.HTTP, 'La entrada no es apta para el análisis de IA.')
                terminada = True
            finally:
                uso = cliente.uso if cliente else {}
                tokens = _tokens(uso)
                tokens_cuota, unidades_cuota = _consumo_confirmado(uso, politica)
                propia = PlanificadorIA.finalizar(
                    clave, propietario, intento, proveedor, round((monotonic() - inicio) * 1000),
                    tokens, error, resultado,
                    incierta=not terminada, actor_id=actor_id,
                    unidades_observadas=_neurons_observados(uso, politica, tokens),
                    tokens_cuota=tokens_cuota, unidades_cuota=unidades_cuota,
                )
            if not propia or not terminada:
                raise TareaIncierta(MENSAJE_INCIERTA)
            if error is None:
                return resultado, f'{proveedor.nombre.capitalize()}/{proveedor.modelo}'
            if error.motivo == Motivo.HTTP:
                raise error from None
            fallback = True
            inicio_espera = monotonic()
        raise AnalisisNoDisponible(
            'Ningún proveedor gratuito autorizado tiene capacidad o devolvió una respuesta válida. '
            'Puede continuar manualmente.'
        )


_ADMINISTRADOR = AdministradorProveedores()


class ConsultaIA:
    def __init__(self, tipo):
        self.tipo = tipo
        self._estado = local()

    @property
    def ultimo_identificador(self):
        return getattr(self._estado, 'ultimo', None)

    def __call__(self, entrada):
        return self.con_ambito(entrada, None)

    def con_ambito(self, entrada, ambito, actor_id=None):
        self._estado.ultimo = None
        resultado, identificador = _ADMINISTRADOR.consultar(self.tipo, entrada, ambito, actor_id)
        self._estado.ultimo = identificador
        return resultado


def obtener_proveedor(tipo):
    if tipo not in _ADAPTADORES:
        raise AnalisisNoDisponible('Tipo de análisis de IA no reconocido.')
    return ConsultaIA(tipo)
