"""Admisión local y serial de un benchmark aislado en un solo proyecto Free Tier."""
from collections import deque
from time import monotonic, sleep


class PresupuestoGoogle:
    rpm = 12
    tpm = 16000
    margen_entrada = 256
    salida = 2048

    def __init__(self, solicitudes, reloj=monotonic, esperar=sleep):
        self.restantes = solicitudes
        self.reloj = reloj
        self.esperar = esperar
        self.recientes = deque()

    def admitir(self, tokens):
        if self.restantes <= 0 or tokens > self.tpm:
            return False
        while True:
            ahora = self.reloj()
            while self.recientes and ahora - self.recientes[0][0] >= 60:
                self.recientes.popleft()
            if (len(self.recientes) < self.rpm
                    and tokens + sum(cargo for _, cargo in self.recientes) <= self.tpm):
                self.restantes -= 1
                return True
            self.esperar(self.recientes[0][0] + 60 - ahora)

    def cerrar(self, tokens):
        # Se mantiene cada reserva 60 s después de recibir la respuesta.
        self.recientes.append((self.reloj(), tokens))
