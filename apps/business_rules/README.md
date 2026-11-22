# Reglas de negocio

Cálculos de la metodología en Python puro (sin Django, sin base de datos):
`funcion_discreta.py`, `il.py` (cuartiles e IL), `is_.py` (IS), `ir.py` (IR y exclusión de IR=1), `pm.py` (ponderación media), `foda.py` (clasificación FODA).

Actualización bibliográfica (HU02): `rules_engine.py` (TC = TC 2021 + aprobadas, r_i, IL, IS),
`glosario_bibliografico.py` (términos en inglés por factor y consulta), `coincidencia.py` (sugerencia de
factores por palabras clave, sin IA) y `publicaciones.py` (DOI normalizado y deduplicación).

Reciben datos y devuelven resultados. Cada regla tiene pruebas en `tests/`; `test_caso_referencia_il_is.py`
valida IL e IS contra el caso de referencia de la metodología GUIOS
(ver «Fundamento metodológico» en el README principal).

