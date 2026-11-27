"""Ejecución acotada de tareas independientes de los servicios de aplicación."""
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.db import close_old_connections, connection, connections

from apps.external_services.proveedor_ia import ConsultaIA


def solicitar(proveedor, entrada, ambito, actor_id):
    if isinstance(proveedor, ConsultaIA):
        return proveedor.con_ambito(entrada, ambito, actor_id)
    return proveedor(entrada)


def en_orden(proveedor, funcion, tareas):
    tareas = list(tareas)
    trabajadores = min(len(tareas), settings.GUIOS_AI_TRABAJADORES_LOTE)
    if trabajadores < 2 or not isinstance(proveedor, ConsultaIA) or connection.in_atomic_block:
        yield from map(funcion, tareas)
        return

    def ejecutar(tarea):
        close_old_connections()
        try:
            return funcion(tarea)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=trabajadores, thread_name_prefix='guios-ia') as executor:
        yield from executor.map(ejecutar, tareas)
