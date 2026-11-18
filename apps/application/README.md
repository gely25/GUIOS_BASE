# Capa de aplicación

Servicios que orquestan los casos de uso. Llaman a `business_rules` para calcular y a `data`
para leer y guardar; no contienen cálculos propios.

Cada archivo de `services/` expone una clase: `AIService`, `BibliographicService`, `CatalogService`,
`DocumentService`, `EvaluationService`, `ReportService`, `RetrievalService`.
`tests/test_servicios.py` comprueba que cada una exista.

Ejemplo completo: `services/indicadores_literatura/` (HU03).
