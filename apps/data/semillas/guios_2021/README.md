# Catálogo GUIOS 2021 (datos semilla)

Los carga `python manage.py cargar_catalogo_guios` como versión `v1-2021`.
Archivos separados por tabuladores, UTF-8 sin BOM.

- `subfactores.tsv`: `Dimensión · Factor · Subfactor` (61 filas). Viene de `guiosad_data.csv` del
  prototipo original, con dos erratas corregidas:
  - «códigofuente» → «código fuente»;
  - «El software es una sistemas de administración de base de datos independiente» →
    «El software es independiente del sistema de administración de base de datos».
- `factores.tsv`: `Factor · Alcance · IE · TC_2021` (18 filas).
  - `Alcance` viene de `factors.csv`.
  - `IE = 3` y `TC_2021` vienen del caso de referencia GUIOS
    (`apps/business_rules/tests/test_caso_referencia_il_is.py`).

La IL y la IS **no se importan**: se recalculan con `business_rules`. La columna `Sugerida` de
`factors.csv` no se usa porque no coincide con el caso de referencia en dos factores
(Usabilidad: 3 frente a 2; Apoyo de la alta dirección: 2 frente a 3), y el caso de referencia
es el que se reproduce con las reglas de GUIOS.
