"""
Vistas de acceso (capa de presentación).

Solo reciben la solicitud y devuelven la pantalla; no hacen cálculos ni
consultan la base de datos directamente.
"""

from django.shortcuts import render


def home_view(request):
    return render(request, 'presentation/acceso/home.html', {'titulo': 'GUIOS PRO'})
