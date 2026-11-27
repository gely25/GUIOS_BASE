import json
import unittest
from contextlib import redirect_stdout
from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from unittest.mock import patch

from benchmarks.casos_ia import CASOS
from benchmarks.clientes_ia import PROVEEDORES_OPERATIVOS, autorizar
from benchmarks.ia import configurar, ejecutar, main


class BenchmarkTests(unittest.TestCase):
    def test_401_y_403_detienen_el_proveedor_y_omiten_el_texto_remoto(self):
        for status in (401, 403):
            with self.subTest(status=status):
                def responder(url, carga, clave, timeout):
                    raise HTTPError(url, status, "privado", {}, BytesIO(
                        b'{"error":{"message":"Invalid API key: secreto-simulado"}}'
                    ))

                filas = ejecutar(configurar(["groq"], "mock", []), "mock", responder)
                self.assertEqual(filas[0]["http_status"], status)
                self.assertIn("clave es inválida", filas[0]["detalle_http"])
                self.assertNotIn("secreto-simulado", json.dumps(filas))
                self.assertTrue(all(x["error"] == f"omitido_por_{status}" for x in filas[1:]))

    def test_configuracion_legada_preserva_modelo_y_prioriza_clave_canonica(self):
        modelo = "openai/gpt-oss-120b"
        with patch("benchmarks.ia.autorizar", return_value="") as validar:
            config = configurar(["groq"], "real", [], {
                "GROQ_MODEL": modelo, "GROQ_API_KEY": "legada",
                "GUIOS_AI_GROQ_API_KEY": "canonica",
            })
        validar.assert_called_once()
        self.assertEqual(config["groq"][:2], (modelo, "canonica"))

    def test_todos_los_casos_mock_sin_red(self):
        with patch("apps.external_services.clientes_ia.build_opener", side_effect=AssertionError("Red")):
            filas = ejecutar(configurar(PROVEEDORES_OPERATIVOS, "mock", []), "mock")
        self.assertEqual(len(filas), 40)
        self.assertTrue(all(x["contrato_valido"] and x["calidad_ok"] for x in filas))

    def test_429_detiene_solo_el_proveedor_afectado(self):
        llamadas = []

        def responder(url, carga, clave, timeout):
            llamadas.append(url)
            if "googleapis" in url:
                raise HTTPError(url, 429, "No exportar este texto", {}, None)
            resultado = CASOS[len(llamadas) - 2].esperado
            return {"choices": [{"message": {"content": json.dumps(resultado)}}]}

        filas = ejecutar(configurar(["gemini", "groq"], "mock", []), "mock", responder)
        self.assertEqual(len(llamadas), 9)
        self.assertEqual(filas[0]["http_status"], 429)
        self.assertTrue(all(x["error"] == "omitido_por_429" for x in filas[1:8]))
        self.assertTrue(all(x["calidad_ok"] for x in filas[8:]))

    def test_json_referencias_y_calidad_se_miden_por_separado(self):
        respuestas = iter([
            '{"sugerencias":[{"publicacion_id":99,"pertinencia":90,"justificacion":"Inventada"}]}',
            '{"sugerencias":[{"publicacion_id":3,"pertinencia":90,"justificacion":"Irrelevante"}]}',
            "{",
            *(json.dumps(caso.esperado) for caso in CASOS[3:]),
        ])

        def responder(url, carga, clave, timeout):
            return {"choices": [{"message": {"content": next(respuestas)}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}}

        filas = ejecutar(configurar(["groq"], "mock", []), "mock", responder)
        self.assertTrue(filas[0]["json_valido"])
        self.assertFalse(filas[0]["contrato_valido"])
        self.assertFalse(filas[0]["referencias_validas"])
        self.assertTrue(filas[1]["contrato_valido"])
        self.assertFalse(filas[1]["calidad_ok"])
        self.assertFalse(filas[2]["json_valido"])
        self.assertEqual(filas[0]["tokens_totales"], 15)

    def test_adaptacion_cohere_y_uso(self):
        casos = iter(CASOS)

        def responder(url, carga, clave, timeout):
            self.assertTrue(url.endswith("/v2/chat"))
            self.assertEqual(carga["response_format"], {"type": "json_object"})
            return {"message": {"content": [{"type": "text", "text": json.dumps(next(casos).esperado)}]},
                    "usage": {"tokens": {"input_tokens": 12, "output_tokens": 3}}}

        filas = ejecutar(configurar(["cohere"], "mock", []), "mock", responder)
        self.assertTrue(all(x["tokens_entrada"] == 12 and x["calidad_ok"] for x in filas))

    def test_openrouter_fija_endpoint_y_desactiva_fallback(self):
        casos = iter(CASOS)

        def responder(url, carga, clave, timeout):
            self.assertEqual(carga["provider"], {
                "only": ["mock"], "allow_fallbacks": False,
                "max_price": {"prompt": 0, "completion": 0, "request": 0},
            })
            return {"choices": [{"message": {"content": json.dumps(next(casos).esperado)}}]}

        filas = ejecutar(configurar(["openrouter"], "mock", []), "mock", responder)
        self.assertTrue(all(x["calidad_ok"] for x in filas))

    def test_cli_real_omite_openrouter_cuando_no_verifica_precio_y_conserva_otros(self):
        configuraciones = {
            "openrouter": ("org/modelo:free", "clave-ficticia", 5, "", "endpoint"),
            "gemini": ("modelo-gemini", "clave-ficticia", 5, "", ""),
        }
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "autorizacion.json"
            ruta.write_text("[]", encoding="utf-8")
            argumentos = ["benchmarks.ia", "--modo", "real", "--proveedores", "openrouter", "gemini",
                          "--autorizacion", str(ruta), "--salida", str(Path(carpeta) / "out")]
            with (patch("sys.argv", argumentos), patch("benchmarks.ia.dotenv_values", return_value={}),
                  patch("benchmarks.ia.configurar", return_value=configuraciones),
                  patch("benchmarks.ia.validar_endpoint_openrouter", side_effect=ValueError) as verificar,
                  patch("benchmarks.ia.ejecutar", return_value=[{"contrato_valido": True}]) as inferir,
                  redirect_stdout(None)):
                main()
        verificar.assert_called_once_with("org/modelo:free", "endpoint", 5)
        self.assertEqual(set(inferir.call_args.args[0]), {("gemini", "modelo-gemini")})

    def test_autorizacion_exige_modelo_exacto_plan_y_fecha(self):
        entrada = {
            "proveedor": "openrouter", "modelo": "org/modelo:free", "plan": "openrouter-free",
            "fuente_oficial": "https://openrouter.ai/org/modelo:free",
            "verificado": "2026-11-26", "vence": "2026-11-26",
            "sin_cargos_ni_excedentes": True, "endpoint_openrouter": "proveedor",
        }
        hoy = date(2026, 11, 26)
        self.assertEqual(autorizar("openrouter", entrada["modelo"], [entrada], hoy), "proveedor")
        exclusiva = entrada | {"uso": "benchmark"}
        self.assertEqual(autorizar("openrouter", entrada["modelo"], [exclusiva], hoy, benchmark=True), "proveedor")
        for cambio in (
            {"modelo": "org/modelo"}, {"modelo": "openrouter/free"}, {"modelo": "openai/modelo:free"},
            {"vence": "2026-11-25"}, {"plan": "pago"}, {"sin_cargos_ni_excedentes": False},
            {"fuente_oficial": "https://ejemplo.com"}, {"endpoint_openrouter": ""},
            {"uso": "benchmark"}, {"uso": "benchmak"},
        ):
            with self.subTest(cambio=cambio), self.assertRaises(ValueError):
                modificada = entrada | cambio
                autorizar("openrouter", modificada["modelo"], [modificada], hoy)
