"""Verificación, migración y medición del piloto local, sin generar inferencias."""
import argparse
import ipaddress
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace


BD_LOCAL = 'guios_pro_ai_dev'
MIGRACION_BASE = ('data', '0016_planificacion_ia')
MIGRACION = ('data', '0017_reconciliacion_ia')
OPERACIONES = {
    'HU02': ('bibliografia',), 'HU09': ('preguntas', 'suficiencia'), 'HU10': ('valoracion',),
}


def destino_local():
    from django.db import connections

    db = connections['default']
    if (db.vendor != 'postgresql' or db.settings_dict['NAME'] != BD_LOCAL
            or db.settings_dict.get('HOST') not in ('localhost', '127.0.0.1', '::1')):
        raise SystemExit('Se requiere PostgreSQL en loopback y la base guios_pro_ai_dev.')
    with db.cursor() as cursor:
        cursor.execute('SELECT current_database(), host(inet_server_addr()), pg_backend_pid()')
        nombre, direccion, pid = cursor.fetchone()
    if nombre != BD_LOCAL or not direccion or not ipaddress.ip_address(direccion).is_loopback:
        raise SystemExit('El servidor conectado no confirma el destino local esperado.')
    if os.name == 'nt':
        verificacion = subprocess.run([
            'powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
            f"if ((Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue).ProcessName -ne 'postgres') {{ exit 1 }}",
        ], capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if verificacion.returncode:
            raise SystemExit('El backend PostgreSQL no se identificó como proceso local de Windows.')
    return db


def migracion_local(aplicar):
    from django.core.management import call_command
    from django.db.migrations.executor import MigrationExecutor

    db = destino_local()
    plan = MigrationExecutor(db).migration_plan([MIGRACION])
    if any(atras or (m.app_label, m.name) not in (MIGRACION_BASE, MIGRACION) for m, atras in plan):
        raise SystemExit('El plan contiene cambios ajenos a 0016/0017 o una reversión. Se cancela.')
    if plan:
        call_command('migrate', *MIGRACION, database='default', plan=not aplicar, interactive=False)
    else:
        print('Las migraciones 0016 y 0017 ya están aplicadas en guios_pro_ai_dev.')


def verificar(perfil):
    from django.conf import settings
    from dotenv import dotenv_values

    from apps.external_services.proveedor_ia import leer_admision

    proveedores, _, _ = leer_admision()
    esperados = {nombre: dato['modelo'] for nombre, dato in perfil['proveedores'].items()}
    efectivos = {p.nombre: p for p in proveedores}
    if len(proveedores) != len(esperados) or {nombre: p.modelo for nombre, p in efectivos.items()} != esperados:
        raise SystemExit('La política, los modelos, las credenciales o la autorización vigente no habilitan exactamente Gemini y Cloudflare.')
    archivo = dotenv_values(settings.BASE_DIR / '.env')
    gemini = (archivo.get('GUIOS_AI_GEMINI_API_KEY') or '').strip()
    cloudflare = ((archivo.get('GUIOS_AI_CLOUDFLARE_API_KEY') or '').strip()
                  or (archivo.get('GUIOS_AI_CLOUDFLARE_API_TOKEN') or '').strip())
    cuenta = (archivo.get('GUIOS_AI_CLOUDFLARE_ACCOUNT_ID') or '').strip()
    if (efectivos['gemini'].clave != gemini or efectivos['cloudflare'].clave != cloudflare
            or efectivos['cloudflare'].cuenta != cuenta):
        raise SystemExit('La terminal está reemplazando las credenciales locales. Revise las variables de proceso.')
    print('Configuración local admitida: Gemini y Cloudflare. Sin solicitudes de IA.')


def verificar_base_migrada():
    from django.db.migrations.recorder import MigrationRecorder

    if MIGRACION not in MigrationRecorder(destino_local()).applied_migrations():
        raise SystemExit('Aplique primero las migraciones locales del planificador hasta 0017.')


def tamanos(perfil):
    from apps.application.services.actualizacion_bibliografica.sugerencias_ia import _entrada as entrada_bib
    from apps.application.services.ai import AIService
    from apps.application.services.suficiencia import _entrada as entrada_hu09
    from apps.external_services.planificador_ia import leer_politicas
    from apps.external_services.proveedor_ia import medir_peticion
    from benchmarks.casos_ia import CASOS

    texto = 'El manual describe la exportación estándar y su configuración. ' * 13
    publicaciones = [{'id': i, 'titulo': f'Publicación sintética {i}', 'resumen': texto + texto[:430]}
                     for i in range(1, 9)]
    evidencias = [{'evidencia_id': i, 'contenido': texto, 'pagina': i} for i in range(1, 13)]
    fila = dict(factor='Interoperabilidad', subfactor='Exportación en formato estándar',
                evidencias=evidencias, preguntas=[], preguntas_descartadas=[])
    muestras = [(caso.id, caso.operacion, caso.entrada) for caso in CASOS] + [
        ('HU02-lote-8', 'bibliografia', entrada_bib(SimpleNamespace(pk=1, nombre=fila['factor']), publicaciones)),
        ('HU09-evidencia-12', 'suficiencia', entrada_hu09(fila)),
        ('HU10-evidencia-12', 'valoracion', AIService._construir_entrada(dict(
            fila, evaluacion_id=1, valoracion_id=1, dimension='Técnica', ir=4,
            suficiencia={'estado': 'SUFICIENCIA_PROPUESTA', 'referencias': ['E:1']},
            sin_informacion=[], fuentes=[
                dict(id=f"E:{e['evidencia_id']}", origen='DOCUMENTO', contenido=e['contenido'], pagina=e['pagina'])
                for e in evidencias
            ],
        ))),
    ]
    politicas = leer_politicas()
    for etiqueta, operacion, entrada in muestras:
        for proveedor, datos in perfil['proveedores'].items():
            politica = politicas[datos['unidad']]
            bytes_http, bytes_entrada = medir_peticion(
                operacion, entrada, proveedor, datos['modelo'], politica.max_tokens_salida,
            )
            reserva = politica.para_peticion(bytes_entrada)
            print(json.dumps({
                'muestra': etiqueta, 'proveedor': proveedor, 'bytes_http': bytes_http,
                'bytes_contexto': bytes_entrada,
                'tokens_reservados': reserva.tokens_por_intento if reserva else None,
                'neurons_reservados': reserva.unidades_por_intento if reserva else None,
            }))


def _actividad(filas, corte):
    eventos = []
    for fila in filas:
        fin = min(fila['fin'] or fila['vence'], corte)
        if fin > fila['inicio']:
            eventos.extend(((fila['inicio'], 1), (fin, -1)))
    activas = pico = 0
    segundos = 0
    anterior = None
    for momento, delta in sorted(eventos):
        if activas:
            segundos += (momento - anterior).total_seconds()
        activas += delta
        pico = max(pico, activas)
        anterior = momento
    tramo = max((momento for momento, _ in eventos)) - min(momento for momento, _ in eventos) if eventos else None
    return pico, round(segundos * 1000), round(tramo.total_seconds() * 1000) if tramo else 0


def resumir(filas, corte, latencia_total_ms):
    por_proveedor = Counter(fila['proveedor'] for fila in filas)
    pico, activo_ms, tramo_ms = _actividad(filas, corte)
    return {
        'latencia_total_ms': latencia_total_ms,
        'ventana_de_ia_ms': tramo_ms,
        'tiempo_con_reservas_abiertas_ms': activo_ms,
        'tiempo_fuera_de_ventana_ia_ms': max(0, latencia_total_ms - tramo_ms),
        'suma_latencias_intentos_ms': sum(fila.get('latencia_ms') or 0 for fila in filas),
        'intentos_reservados': len(filas),
        'intentos_por_proveedor': dict(por_proveedor),
        'tokens_observados': sum(fila['tokens_observados'] or 0 for fila in filas),
        'intentos_con_tokens_observados': sum(fila['tokens_observados'] is not None for fila in filas),
        'tokens_reservados': sum(fila['tokens_reservados'] for fila in filas),
        'tokens_cuota': sum(fila.get('tokens_contabilizados', fila['tokens_reservados']) for fila in filas),
        'neurons_reservados': sum(fila['unidades_reservadas'] for fila in filas),
        'neurons_contabilizados': sum(fila.get('neurons_contabilizados', fila['unidades_reservadas']) for fila in filas),
        'concurrencia_pico': pico,
        'concurrencia_pico_por_proveedor': {
            proveedor: _actividad([f for f in filas if f['proveedor'] == proveedor], corte)[0]
            for proveedor in por_proveedor
        },
        'intentos_abiertos_al_cierre': sum(fila['fin'] is None for fila in filas),
        'fallbacks': sum(fila['fallback'] for fila in filas),
        'errores': dict(Counter(fila['error'] for fila in filas if fila['error'])),
        'intentos': filas,
    }


def medir(hu, salida):
    from apps.data.models import IntentoIA
    from apps.external_services.planificador_ia import _ahora, cargos_cuota

    verificar_base_migrada()
    if salida.exists():
        raise SystemExit('La salida ya existe. Indique un archivo nuevo.')
    inicio_bd = _ahora()
    inicio = perf_counter()
    input(f'{hu}: ejecute solo este flujo con datos sintéticos/anonimizados y pulse Intro al terminar. ')
    latencia = round((perf_counter() - inicio) * 1000)
    corte = _ahora()
    tokens, neurons = cargos_cuota()
    filas = list(IntentoIA.objects.filter(operacion__in=OPERACIONES[hu], inicio__gte=inicio_bd, inicio__lte=corte)
                 .annotate(tokens_contabilizados=tokens, neurons_contabilizados=neurons)
                 .order_by('inicio', 'pk').values(
        'proveedor', 'modelo', 'operacion', 'inicio', 'fin', 'vence', 'latencia_ms', 'espera_ms',
        'tokens_observados', 'tokens_reservados', 'unidades_reservadas', 'fallback', 'error',
        'tokens_contabilizados', 'neurons_contabilizados',
    ))
    for fila in filas:
        if fila['fin'] and fila['fin'] > corte:
            fila.update(fin=None, latencia_ms=None, tokens_observados=None, error='',
                        tokens_contabilizados=fila['tokens_reservados'],
                        neurons_contabilizados=fila['unidades_reservadas'])
    resumen = dict(hu=hu, **resumir(filas, corte, latencia))
    with salida.open('x', encoding='utf-8') as archivo:
        json.dump(resumen, archivo, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: v for k, v in resumen.items() if k != 'intentos'}, ensure_ascii=False, indent=2))


def cuotas():
    from django.db import transaction
    from django.db.migrations.recorder import MigrationRecorder
    from django.db.models import Count, Sum

    from apps.data.models import IntentoIA, UnidadCuotaIA
    from apps.external_services.planificador_ia import _ahora, _MEDIDAS, cargos_cuota, consumo_ventana
    from apps.external_services.proveedor_ia import leer_admision

    _, politicas, _ = leer_admision()
    if not politicas:
        raise SystemExit('Cargue primero el perfil operativo para consultar sus presupuestos.')
    db = destino_local()
    with transaction.atomic():
        with db.cursor() as cursor:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        aplicadas = MigrationRecorder(db).applied_migrations()
        if MIGRACION_BASE not in aplicadas:
            raise SystemExit('La base local todavía no tiene el registro de intentos.')
        reconciliacion = MIGRACION in aplicadas
        momento = _ahora()
        tokens, neurons = cargos_cuota(reconciliacion)
        historico = list(IntentoIA.objects.filter(operacion='bibliografia').values('proveedor').annotate(
            intentos=Count('id'), tokens_admitidos=Sum('tokens_reservados'),
            tokens_observados_hu02=Sum('tokens_observados'), tokens_contabilizados=Sum(tokens),
            neurons_contabilizados=Sum(neurons),
        ).order_by('proveedor'))
        unidades = {}
        cooldowns = dict(UnidadCuotaIA.objects.filter(pk__in=politicas).values_list('pk', 'cooldown_hasta'))
        for unidad, politica in politicas.items():
            intentos = IntentoIA.objects.filter(unidad_id=unidad)
            ventanas = {segundos: consumo_ventana(intentos, momento, segundos, reconciliacion)
                        for segundos in {_MEDIDAS[nombre][0] for nombre in politica.ventanas}}
            saldos = {}
            for nombre, limite in politica.ventanas.items():
                segundos, medida = _MEDIDAS[nombre]
                usado = ventanas[segundos][medida]
                saldos[nombre] = {'tope': limite, 'usado': usado, 'restante': max(0, limite - usado)}
            saldos['concurrencia'] = {
                'tope': politica.concurrencia,
                'en_curso': intentos.filter(fin__isnull=True, vence__gt=momento).count(),
            }
            hasta = cooldowns.get(unidad)
            saldos['cooldown_hasta'] = hasta if hasta and hasta > momento else None
            unidades[unidad] = saldos
    print(json.dumps({'corte_utc': momento, 'hu02_acumulado': historico, 'ventanas': unidades},
                     ensure_ascii=False, default=str, indent=2))


def preparar_hu09(evaluacion, decisor):
    from django.core.exceptions import PermissionDenied

    from apps.application.services.lotes_hu09 import ACTIVOS, LotesHU09Service
    from apps.application.services.preguntas import PreguntasService
    from apps.application.services.suficiencia import _entrada
    from apps.data.models import LoteHU09, Usuario
    from apps.external_services.proveedor_ia import leer_admision, medir_peticion

    verificar_base_migrada()
    actor = Usuario.objects.filter(pk=decisor, rol=Usuario.DECISOR, activo=True).first()
    if not actor:
        raise SystemExit('El decisor indicado no está activo o no existe.')
    try:
        evaluacion_obj = PreguntasService._evaluacion(actor, evaluacion)
        objetivos = LotesHU09Service.objetivos(actor, evaluacion)
    except PermissionDenied:
        raise SystemExit('La evaluación no está disponible para ese decisor.') from None
    if (evaluacion_obj.estado != 'EN_PROCESO' or evaluacion_obj.fecha_fin is not None
            or LoteHU09.objects.filter(evaluacion_id=evaluacion, estado__in=ACTIVOS).exists()):
        raise SystemExit('La evaluación no está abierta para un lote nuevo.')
    if len(objetivos) != 2:
        raise SystemExit(f'Se detectaron {len(objetivos)} subfactores elegibles; la prueba controlada requiere dos.')
    proveedores, politicas, por_modelo = leer_admision()
    filas = [fila for fila in PreguntasService.contexto(actor, evaluacion) if fila['valoracion_id'] in objetivos]
    estimaciones = {}
    for proveedor in proveedores:
        if 'suficiencia' not in proveedor.operaciones or proveedor.unidad_cuota not in politicas:
            continue
        politica = por_modelo.get(proveedor.identificador_config, politicas[proveedor.unidad_cuota])
        costes = []
        for fila in filas:
            _, contexto = medir_peticion('suficiencia', _entrada(fila), proveedor.nombre, proveedor.modelo,
                                         politica.max_tokens_salida, proveedor.endpoint)
            coste = politica.para_peticion(contexto)
            if coste is None or not coste.cabe_en(politicas[proveedor.unidad_cuota]) or not coste.cabe_en(politica):
                raise SystemExit('El contexto de un subfactor supera el techo de reserva del perfil.')
            costes.append(coste)
        estimaciones[proveedor.nombre] = {
            'tokens_reservados_si_atendiera_ambos': sum(c.tokens_por_intento for c in costes),
            'neurons_reservados_si_atendiera_ambos': sum(c.unidades_por_intento for c in costes),
        }
    if not estimaciones:
        raise SystemExit('El perfil no tiene un proveedor autorizado para suficiencia.')
    print(json.dumps({'subfactores': objetivos, 'estimaciones': estimaciones, 'lote_creado': False}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('accion', choices=('verificar', 'plan', 'migrar', 'tamanos', 'medir', 'cuotas', 'preparar-hu09'))
    parser.add_argument('--perfil', type=Path, default=Path('config/ia-local.json'))
    parser.add_argument('--hu', choices=OPERACIONES)
    parser.add_argument('--salida', type=Path)
    parser.add_argument('--base', action='store_true')
    parser.add_argument('--evaluacion', type=int)
    parser.add_argument('--decisor', type=int)
    args = parser.parse_args()
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    import django

    django.setup()
    if args.accion in ('plan', 'migrar'):
        migracion_local(args.accion == 'migrar')
    elif args.accion == 'cuotas':
        cuotas()
    elif args.accion == 'preparar-hu09':
        if not args.evaluacion or not args.decisor:
            parser.error('preparar-hu09 requiere --evaluacion y --decisor.')
        preparar_hu09(args.evaluacion, args.decisor)
    elif args.accion == 'medir':
        if not args.hu or not args.salida:
            parser.error('medir requiere --hu y --salida.')
        medir(args.hu, args.salida)
    else:
        perfil = json.loads(args.perfil.read_text(encoding='utf-8-sig'))
        if args.accion == 'tamanos':
            tamanos(perfil)
        else:
            verificar(perfil)
            if args.base:
                verificar_base_migrada()


if __name__ == '__main__':
    main()
