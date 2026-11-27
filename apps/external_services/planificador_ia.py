"""Admisión y deduplicación transaccionales. Ningún método hace I/O de proveedor."""
import json
from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import uuid4

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, F, PositiveBigIntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, Greatest

from apps.data.models import CredencialBloqueadaIA, IntentoIA, TareaIA, UnidadCuotaIA
from apps.external_services.ai_errors import AnalisisNoDisponible, Motivo


_MEDIDAS = {
    'rpm': (60, 'peticiones'), 'rpd': (86400, 'peticiones'),
    'rp31d': (31 * 86400, 'peticiones'),
    'tpm': (60, 'tokens'), 'tpd': (86400, 'tokens'),
    'unidades_diarias': (86400, 'unidades'),
}
_RECHAZOS = {Motivo.NO_AUTENTICADO, Motivo.PROHIBIDO}
_TRANSITORIOS = {Motivo.CUOTA, Motivo.SERVIDOR, Motivo.TIMEOUT, Motivo.RED}


@dataclass(frozen=True)
class PoliticaCuota:
    concurrencia: int
    ventanas: dict
    tokens_por_intento: int
    max_tokens_salida: int
    unidades_por_intento: int
    margen_tokens_entrada: int | None = None
    neurons_por_millon_entrada: int = 0
    neurons_por_millon_salida: int = 0
    reconciliar_uso: bool = False

    def calcular_neurons(self, entrada, salida):
        cargo_entrada = (entrada * self.neurons_por_millon_entrada + 999_999) // 1_000_000
        cargo_salida = (salida * self.neurons_por_millon_salida + 999_999) // 1_000_000
        return cargo_entrada + cargo_salida

    def para_peticion(self, bytes_entrada):
        if self.margen_tokens_entrada is None:
            return self
        entrada = bytes_entrada + self.margen_tokens_entrada
        total = entrada + self.max_tokens_salida
        if total > self.tokens_por_intento:
            return None
        unidades = self.unidades_por_intento
        if self.neurons_por_millon_entrada:
            unidades = self.calcular_neurons(entrada, self.max_tokens_salida)
        return replace(self, tokens_por_intento=total, unidades_por_intento=unidades)

    def cabe_en(self, politica):
        cargos = {'peticiones': 1, 'tokens': self.tokens_por_intento, 'unidades': self.unidades_por_intento}
        return all(cargos[_MEDIDAS[nombre][1]] <= limite for nombre, limite in politica.ventanas.items())


def _positivo(valor):
    return type(valor) is int and 0 < valor <= 2**31 - 1


def _configuracion_json(nombre):
    try:
        datos = json.loads(getattr(settings, nombre, '{}'))
    except (ValueError, TypeError):
        return {}
    return datos if isinstance(datos, dict) else {}


def leer_politicas(variable='GUIOS_AI_POLITICAS_CUOTA'):
    politicas = {}
    for unidad, datos in _configuracion_json(variable).items():
        if not isinstance(datos, dict) or not {'rpm', 'tpm', 'rpd'} <= datos.keys():
            continue
        ventanas = {nombre: datos[nombre] for nombre in _MEDIDAS if datos.get(nombre) is not None}
        concurrencia = datos.get('concurrencia', 1)
        salida = datos.get('max_tokens_salida')
        reserva = datos.get('tokens_por_intento')
        unidades = datos.get('unidades_por_intento', 0)
        margen = datos.get('margen_tokens_entrada')
        tasa_entrada = datos.get('neurons_por_millon_entrada', 0)
        tasa_salida = datos.get('neurons_por_millon_salida', 0)
        reconciliar = datos.get('reconciliar_uso', False)
        if (not ventanas or not all(_positivo(v) for v in ventanas.values())
                or not _positivo(concurrencia) or not _positivo(salida)
                or not _positivo(reserva) or reserva <= salida or type(reconciliar) is not bool):
            continue
        if margen is not None and not _positivo(margen):
            continue
        if tasa_entrada or tasa_salida:
            if (margen is None or 'unidades_diarias' not in ventanas
                    or not _positivo(tasa_entrada) or not _positivo(tasa_salida) or unidades):
                continue
        elif 'unidades_diarias' in ventanas and not _positivo(unidades):
            continue
        politicas[unidad] = PoliticaCuota(concurrencia, ventanas, reserva, salida,
                                        unidades if 'unidades_diarias' in ventanas else 0,
                                        margen, tasa_entrada, tasa_salida, reconciliar)
    return politicas


def leer_perfiles():
    return _configuracion_json('GUIOS_AI_PERFILES_OPERACION')


def leer_modelos_adicionales():
    return _configuracion_json('GUIOS_AI_MODELOS_ADICIONALES')


def politicas_compartidas(politicas, proveedores, por_modelo):
    """Mantiene un solo contador por proyecto aun cuando se desconoce su independencia."""
    proyectos = dict(politicas)
    for proveedor in proveedores:
        modelo = por_modelo.get(proveedor.identificador_config)
        if modelo is None:
            continue
        proyecto = proyectos[proveedor.unidad_cuota]
        ventanas = dict(proyecto.ventanas)
        for nombre, limite in modelo.ventanas.items():
            ventanas[nombre] = min(ventanas.get(nombre, limite), limite)
        proyectos[proveedor.unidad_cuota] = replace(proyecto, ventanas=ventanas)
    return proyectos


def _orden(proveedor, tipo, perfiles, activas):
    clave = f'{proveedor.nombre}/{proveedor.modelo}'
    por_operacion = perfiles.get(clave, {})
    datos = por_operacion.get(tipo, {}) if isinstance(por_operacion, dict) else {}
    calidad = datos.get('calidad') if isinstance(datos, dict) else None
    latencia = datos.get('latencia_ms') if isinstance(datos, dict) else None
    if (type(calidad) in (int, float) and 0 <= calidad <= 1
            and type(latencia) in (int, float) and 0 < latencia < float('inf')):
        return (0, -calidad, latencia * (activas + 1), proveedor.nombre)
    return (1, proveedor.nombre != 'gemini', activas, proveedor.nombre)


def _ahora():
    # El reloj de PostgreSQL se comparte entre los procesos que reservan.
    with connection.cursor() as cursor:
        cursor.execute('SELECT clock_timestamp()')
        return cursor.fetchone()[0]


def _duracion_reserva():
    return timedelta(seconds=max(settings.GUIOS_AI_RESERVA_SEGUNDOS,
                                 settings.GUIOS_AI_TIMEOUT + settings.GUIOS_AI_ESPERA_SEGUNDOS + 5))


def cargos_cuota(reconciliacion=True):
    tokens = Greatest(F('tokens_reservados'), F('tokens_observados'))
    unidades = F('unidades_reservadas')
    if reconciliacion:
        tokens = Coalesce('tokens_cuota', tokens)
        unidades = Coalesce('unidades_cuota', unidades)
    return tokens, unidades


def consumo_ventana(intentos, momento, segundos, reconciliacion=True):
    desde = momento - timedelta(seconds=segundos)
    tokens, unidades = cargos_cuota(reconciliacion)
    consumos = intentos.filter(Q(inicio__gt=desde) | Q(fin__gt=desde)
                              | Q(fin__isnull=True, vence__gt=desde)).aggregate(
        peticiones=Count('pk'), tokens=Sum(tokens), unidades=Sum(unidades),
    )
    return {medida: cantidad or 0 for medida, cantidad in consumos.items()}


def _hay_cuota(intentos, politica, momento, coste, consumos=None):
    cargos = {'peticiones': 1, 'tokens': coste.tokens_por_intento, 'unidades': coste.unidades_por_intento}
    if consumos is None:
        consumos = {}
    for nombre, limite in politica.ventanas.items():
        segundos, medida = _MEDIDAS[nombre]
        if segundos not in consumos:
            consumos[segundos] = consumo_ventana(intentos, momento, segundos)
        if consumos[segundos][medida] + cargos[medida] > limite:
            return False
    return True


class TareaEnCurso(AnalisisNoDisponible):
    pass


class TareaIncierta(AnalisisNoDisponible):
    pass


MENSAJE_INCIERTA = 'El intento anterior puede seguir activo. Continúe manualmente o verifique su término antes de reabrir la tarea.'


class PlanificadorIA:
    @staticmethod
    def _abandonar(tarea):
        abandonados = tarea.intentos.filter(fin__isnull=True)
        if not abandonados.update(error='reserva_abandonada', fin=F('vence')):
            return False
        tarea.estado = TareaIA.Estado.INCIERTA
        tarea.propietario = None
        return True

    @staticmethod
    def tomar(clave, actor_id=None):
        with transaction.atomic():
            tarea, _ = TareaIA.objects.select_for_update().get_or_create(pk=clave)
            momento = _ahora()
            if tarea.estado == TareaIA.Estado.COMPLETADA and tarea.vence > momento:
                cache = tarea.resultado
                if (not isinstance(cache, dict) or 'actor_id' not in cache
                        or cache['actor_id'] != actor_id or 'respuesta' not in cache):
                    raise AnalisisNoDisponible(
                        'Hay un resultado previo que no se puede reutilizar en esta sesión. Puede continuar manualmente.'
                    )
                return None, (cache['respuesta'], tarea.identificador)
            if tarea.estado == TareaIA.Estado.INCIERTA:
                raise TareaIncierta(MENSAJE_INCIERTA)
            if tarea.estado == TareaIA.Estado.EN_CURSO and tarea.vence > momento:
                raise TareaEnCurso('Ya hay una solicitud de IA para este contexto.')
            if not (tarea.estado == TareaIA.Estado.EN_CURSO and PlanificadorIA._abandonar(tarea)):
                tarea.estado = TareaIA.Estado.EN_CURSO
                tarea.propietario = uuid4()
                tarea.vence = momento + _duracion_reserva()
            tarea.resultado = None
            tarea.identificador = ''
            tarea.save()
        if tarea.estado == TareaIA.Estado.INCIERTA:
            raise TareaIncierta(MENSAJE_INCIERTA)
        return tarea.propietario, None

    @staticmethod
    @transaction.atomic
    def reservar(clave, propietario, tipo, candidatos, politicas, perfiles, espera_ms, fallback,
                 costes=None, politicas_modelo=None):
        tarea = TareaIA.objects.select_for_update().get(pk=clave)
        if tarea.propietario != propietario or tarea.estado != TareaIA.Estado.EN_CURSO:
            raise TareaIncierta(MENSAJE_INCIERTA)
        # Orden común de bloqueo para todas las combinaciones de unidades.
        unidades = {
            pk: UnidadCuotaIA.objects.select_for_update().get_or_create(pk=pk)[0]
            for pk in sorted({p.unidad_cuota for p in candidatos})
        }
        momento = _ahora()
        if tarea.vence <= momento:
            raise TareaEnCurso('Expiró la espera para reservar capacidad de IA.')
        if tarea.intentos.filter(fin__isnull=True).exists():
            raise TareaEnCurso('Ya hay un intento reservado para este contexto.')
        rechazadas = set(CredencialBloqueadaIA.objects.filter(
            pk__in=[p.credencial for p in candidatos]).values_list('pk', flat=True))
        disponibles = []
        for pk, unidad in unidades.items():
            politica = politicas[pk]
            if unidad.cooldown_hasta and unidad.cooldown_hasta > momento:
                continue
            intentos = IntentoIA.objects.filter(unidad=unidad)
            activas = intentos.filter(fin__isnull=True, vence__gt=momento).count()
            if activas >= politica.concurrencia:
                continue
            consumos_proyecto = {}
            for candidato in candidatos:
                if candidato.unidad_cuota != pk or candidato.credencial in rechazadas:
                    continue
                coste = costes[candidato] if costes is not None else politica
                if not _hay_cuota(intentos, politica, momento, coste, consumos_proyecto):
                    continue
                politica_modelo = (politicas_modelo or {}).get(candidato.identificador_config)
                ocupacion = activas
                if politica_modelo:
                    intentos_modelo = intentos.filter(proveedor=candidato.nombre, modelo=candidato.modelo)
                    activas_modelo = intentos_modelo.filter(fin__isnull=True, vence__gt=momento).count()
                    if (activas_modelo >= politica_modelo.concurrencia
                            or not _hay_cuota(intentos_modelo, politica_modelo, momento, coste)):
                        continue
                    ocupacion = activas_modelo
                disponibles.append((candidato, ocupacion, coste))
        if not disponibles:
            return None, len(rechazadas) < len({p.credencial for p in candidatos})
        proveedor, _, politica = min(disponibles, key=lambda par: _orden(par[0], tipo, perfiles, par[1]))
        tarea.vence = momento + _duracion_reserva()
        tarea.save(update_fields=['vence'])
        intento = IntentoIA.objects.create(
            tarea=tarea, unidad=unidades[proveedor.unidad_cuota], proveedor=proveedor.nombre,
            modelo=proveedor.modelo, operacion=tipo, inicio=momento, vence=tarea.vence,
            tokens_reservados=politica.tokens_por_intento, unidades_reservadas=politica.unidades_por_intento,
            espera_ms=espera_ms, fallback=fallback,
        )
        return (proveedor, politica, intento.pk), False

    @staticmethod
    @transaction.atomic
    def finalizar(clave, propietario, intento_id, proveedor, latencia_ms, tokens, error=None,
                  resultado=None, incierta=False, actor_id=None, unidades_observadas=0,
                  tokens_cuota=None, unidades_cuota=None):
        tarea = TareaIA.objects.select_for_update().get(pk=clave)
        if tarea.propietario != propietario or tarea.estado != TareaIA.Estado.EN_CURSO:
            # Una reclamación posterior ya cercó al dueño original. No publica una respuesta tardía.
            return False
        unidad = UnidadCuotaIA.objects.select_for_update().get(pk=proveedor.unidad_cuota)
        momento = _ahora()
        estado_error = error.motivo.value if error else ('indeterminado' if incierta else '')
        if error or incierta:
            tokens_cuota = unidades_cuota = None
        if unidades_cuota is None and unidades_observadas:
            unidades_cuota = Greatest('unidades_reservadas', Value(unidades_observadas, PositiveBigIntegerField()))
        cerrados = IntentoIA.objects.filter(
            pk=intento_id, tarea=tarea, unidad=unidad, proveedor=proveedor.nombre,
            modelo=proveedor.modelo, fin__isnull=True,
        ).update(
            fin=momento, latencia_ms=latencia_ms, tokens_observados=tokens, error=estado_error,
            tokens_cuota=tokens_cuota, unidades_cuota=unidades_cuota,
        )
        if not cerrados:
            return False
        if error and error.motivo in _RECHAZOS:
            CredencialBloqueadaIA.objects.get_or_create(pk=proveedor.credencial,
                                                       defaults={'estado_http': int(error.motivo.value)})
        if incierta or (error and error.motivo in _TRANSITORIOS):
            pausa = max(settings.GUIOS_AI_COOLDOWN, (error.retry_after or 0) if error else 0)
            if incierta:
                pausa = max(pausa, _duracion_reserva().total_seconds())
            try:
                hasta = momento + timedelta(seconds=pausa)
            except OverflowError:
                hasta = momento.max.replace(tzinfo=momento.tzinfo)
            if not unidad.cooldown_hasta or hasta > unidad.cooldown_hasta:
                unidad.cooldown_hasta = hasta
                unidad.save(update_fields=['cooldown_hasta'])
        if incierta:
            tarea.estado = TareaIA.Estado.INCIERTA
            tarea.propietario = None
        elif error is None:
            tarea.estado = TareaIA.Estado.COMPLETADA
            tarea.propietario = None
            tarea.vence = momento + timedelta(seconds=settings.GUIOS_AI_REUSO_SEGUNDOS)
            tarea.resultado = {'actor_id': actor_id, 'respuesta': resultado}
            tarea.identificador = f'{proveedor.nombre.capitalize()}/{proveedor.modelo}'
        tarea.save()
        return True

    @staticmethod
    def liberar(clave, propietario):
        # Solo una tarea sin un intento en curso puede volver a quedar disponible.
        with transaction.atomic():
            tarea = TareaIA.objects.select_for_update().get(pk=clave)
            if tarea.propietario == propietario and not tarea.intentos.filter(fin__isnull=True).exists():
                tarea.estado = TareaIA.Estado.DISPONIBLE
                tarea.propietario = None
                tarea.vence = None
                tarea.save(update_fields=['estado', 'propietario', 'vence'])

    @staticmethod
    @transaction.atomic
    def mantener(limite=100):
        momento = _ahora()
        tareas = list(TareaIA.objects.select_for_update(skip_locked=True).filter(
            estado__in=(TareaIA.Estado.EN_CURSO, TareaIA.Estado.COMPLETADA), vence__lte=momento,
        ).order_by('vence', 'pk')[:limite])
        for tarea in tareas:
            if tarea.estado != TareaIA.Estado.EN_CURSO or not PlanificadorIA._abandonar(tarea):
                tarea.estado = TareaIA.Estado.DISPONIBLE
            tarea.propietario = None
            tarea.vence = None
            tarea.resultado = None
            tarea.identificador = ''
            tarea.save()
        return len(tareas)

    @staticmethod
    @transaction.atomic
    def reabrir_confirmada(clave):
        return TareaIA.objects.filter(pk=clave, estado=TareaIA.Estado.INCIERTA).update(
            estado=TareaIA.Estado.DISPONIBLE, propietario=None, vence=None,
        )
