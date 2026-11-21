"""
Servicio de Aplicación: RetrievalService.

Capa: application. Embeddings de 1536 dimensiones y recuperación de evidencia
por similitud semántica con pgvector (HU08).
"""

import hashlib
import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence

from django.core.exceptions import ValidationError
from pgvector.django import CosineDistance

from apps.data.models import FragmentoDocumento, Subfactor
from apps.data.models.documentos import DIMENSIONES_EMBEDDING


class RetrievalService:
    """Embeddings y recuperación de evidencia por similitud con pgvector (HU08)."""

    DIMENSIONES = DIMENSIONES_EMBEDDING  # 1536

    STOPWORDS = {
        'a', 'al', 'algo', 'algunas', 'algunos', 'ante', 'antes', 'como', 'con',
        'contra', 'cual', 'cuando', 'de', 'del', 'desde', 'donde', 'durante',
        'e', 'el', 'ella', 'ellas', 'ellos', 'en', 'entre', 'era', 'es', 'esa',
        'esas', 'ese', 'eso', 'esos', 'esta', 'estas', 'este', 'esto', 'estos',
        'fue', 'ha', 'han', 'hasta', 'hay', 'la', 'las', 'le', 'les', 'lo',
        'los', 'mas', 'me', 'mi', 'muy', 'no', 'nos', 'o', 'os', 'otra', 'otras',
        'otro', 'otros', 'para', 'pero', 'por', 'porque', 'que', 'quien', 'se',
        'sea', 'ser', 'si', 'sin', 'sobre', 'son', 'su', 'sus', 'tambien', 'te',
        'tiene', 'tienen', 'todo', 'todos', 'un', 'una', 'uno', 'unos', 'y', 'ya',
        'the', 'and', 'of', 'to', 'in', 'is', 'for', 'on', 'with', 'as', 'by',
    }

    @staticmethod
    def _normalizar_texto(texto: str) -> str:
        sin_acentos = ''.join(
            c for c in unicodedata.normalize('NFKD', texto.lower())
            if not unicodedata.combining(c)
        )
        return re.sub(r'\s+', ' ', sin_acentos).strip()

    def _extraer_caracteristicas(self, texto_normalizado: str) -> Dict[str, float]:
        """Extrae términos relevantes, raíces morfológicas, bigramas y n-gramas."""
        tokens_brutos = re.findall(r'[a-z0-9]{2,}', texto_normalizado)
        tokens = [t for t in tokens_brutos if t not in self.STOPWORDS]
        if not tokens:
            tokens = tokens_brutos

        pesos: Dict[str, float] = {}

        for token in tokens:
            clave_tok = f'tok:{token}'
            pesos[clave_tok] = pesos.get(clave_tok, 0.0) + 2.0

            if len(token) >= 5:
                raiz = token[:5]
                clave_raiz = f'root:{raiz}'
                pesos[clave_raiz] = pesos.get(clave_raiz, 0.0) + 1.25

        for i in range(len(tokens) - 1):
            bigrama = f'bi:{tokens[i]}_{tokens[i + 1]}'
            pesos[bigrama] = pesos.get(bigrama, 0.0) + 1.5

        compacto = ' '.join(tokens)
        if len(compacto) >= 4:
            for i in range(len(compacto) - 3):
                ng = compacto[i:i + 4]
                if ' ' not in ng:
                    clave_ng = f'ng:{ng}'
                    pesos[clave_ng] = pesos.get(clave_ng, 0.0) + 0.35

        return {k: 1.0 + math.log(v) for k, v in pesos.items() if v > 0}

    def generar_embedding(self, texto: str) -> List[float]:
        """
        Genera un vector denso normalizado (L2 = 1.0) de 1536 dimensiones
        compatible con pgvector y CosineDistance.
        """
        if not isinstance(texto, str) or not texto.strip():
            raise ValidationError('El texto para generar el embedding no puede estar vacío.')

        normalizado = self._normalizar_texto(texto)
        caracteristicas = self._extraer_caracteristicas(normalizado)
        vector = [0.0] * self.DIMENSIONES

        if not caracteristicas:
            caracteristicas = {f'raw:{normalizado}': 1.0}

        for rasgo, peso in caracteristicas.items():
            digest = hashlib.blake2b(rasgo.encode('utf-8'), digest_size=16).digest()
            for k in range(4):
                bloque = int.from_bytes(digest[k * 4:(k + 1) * 4], 'big')
                indice = (bloque >> 1) % self.DIMENSIONES
                signo = 1.0 if (bloque & 1) == 0 else -1.0
                vector[indice] += signo * peso

        norma = math.sqrt(sum(v * v for v in vector))
        if norma == 0.0:
            vector[0] = 1.0
            return vector

        return [round(v / norma, 8) for v in vector]

    def generar_embeddings_lote(self, textos: Sequence[str]) -> List[List[float]]:
        """Genera embeddings de 1536 dimensiones para una lista de textos."""
        return [self.generar_embedding(t) for t in textos]

    def indexar_fragmentos(
        self,
        fragmentos: Iterable[FragmentoDocumento],
        guardar: bool = True,
    ) -> int:
        """
        Calcula y asigna el embedding a una colección de FragmentoDocumento.
        Si guardar=True, persiste los vectores en PostgreSQL mediante bulk_update.
        """
        lista = list(fragmentos)
        if not lista:
            return 0

        for frag in lista:
            frag.embedding = self.generar_embedding(frag.contenido)

        if guardar:
            FragmentoDocumento.objects.bulk_update(lista, ['embedding'], batch_size=100)

        return len(lista)

    def sincronizar_evaluacion(
        self,
        evaluacion_id: Optional[int] = None,
        forzar: bool = False,
    ) -> Dict[str, int]:
        """
        Genera embeddings para fragmentos pendientes (o todos si forzar=True).
        """
        qs = FragmentoDocumento.objects.all().order_by('fragmento_id')
        if evaluacion_id is not None:
            qs = qs.filter(documento__evaluacion_id=evaluacion_id)
        if not forzar:
            qs = qs.filter(embedding__isnull=True)

        fragmentos = list(qs)
        indexados = self.indexar_fragmentos(fragmentos, guardar=True)
        return {
            'procesados': len(fragmentos),
            'indexados': indexados,
        }

    @staticmethod
    def _formatear_ubicacion(fragmento: FragmentoDocumento) -> str:
        if fragmento.pagina:
            return f'Página {fragmento.pagina}'
        if fragmento.seccion:
            return f'Sección: {fragmento.seccion}'
        if fragmento.hoja:
            return f'Hoja: {fragmento.hoja}'
        return f'Fragmento #{fragmento.fragmento_id}'

    def buscar_evidencia(
        self,
        evaluacion_id: int,
        consulta: str,
        top_k: int = 5,
        umbral_similitud: float = 0.0,
        documento_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Recupera los fragmentos más relevantes de una evaluación usando
        distancia coseno nativa de pgvector (<=>).
        """
        if not isinstance(consulta, str) or not consulta.strip():
            raise ValidationError('La consulta de búsqueda semántica no puede estar vacía.')

        if top_k < 1:
            raise ValidationError('El parámetro top_k debe ser mayor o igual a 1.')

        vector_consulta = self.generar_embedding(consulta)

        qs = FragmentoDocumento.objects.select_related('documento').filter(
            documento__evaluacion_id=evaluacion_id,
            embedding__isnull=False,
        )
        if documento_id is not None:
            qs = qs.filter(documento_id=documento_id)

        candidatos = (
            qs.annotate(distancia=CosineDistance('embedding', vector_consulta))
            .order_by('distancia', 'fragmento_id')[:top_k]
        )

        resultados: List[Dict[str, Any]] = []
        for frag in candidatos:
            distancia = float(frag.distancia)
            similitud = max(0.0, min(1.0, round(1.0 - distancia, 4)))
            if similitud < umbral_similitud:
                continue

            resultados.append({
                'fragmento_id': frag.fragmento_id,
                'documento_id': frag.documento_id,
                'documento_nombre': frag.documento.nombre,
                'documento_tipo': frag.documento.tipo,
                'pagina': frag.pagina,
                'seccion': frag.seccion,
                'hoja': frag.hoja,
                'ubicacion_referencia': self._formatear_ubicacion(frag),
                'contenido': frag.contenido,
                'distancia': round(distancia, 6),
                'similitud': similitud,
                'relevancia_porcentaje': round(similitud * 100, 2),
            })

        return resultados

    def buscar_por_subfactor(
        self,
        evaluacion_id: int,
        subfactor_id: int,
        top_k: int = 5,
        umbral_similitud: float = 0.0,
        documento_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Busca los fragmentos de la evaluación consultada relacionados con un Subfactor
        del catálogo (combinando su Factor y descripción).
        """
        subfactor = (
            Subfactor.objects.select_related('factor', 'factor__dimension')
            .filter(subfactor_id=subfactor_id)
            .first()
        )
        if not subfactor:
            raise ValidationError(f'No existe el subfactor con ID {subfactor_id}.')

        consulta_subfactor = f'{subfactor.factor.nombre}: {subfactor.descripcion}'
        resultados = self.buscar_evidencia(
            evaluacion_id=evaluacion_id,
            consulta=consulta_subfactor,
            top_k=top_k,
            umbral_similitud=umbral_similitud,
            documento_id=documento_id,
        )

        for item in resultados:
            item['subfactor_id'] = subfactor.subfactor_id
            item['subfactor_descripcion'] = subfactor.descripcion
            item['factor_nombre'] = subfactor.factor.nombre

        return resultados

    def buscar_por_subfactores(
        self,
        evaluacion_id: int,
        subfactor_ids: Optional[Sequence[int]] = None,
        top_k: int = 3,
        umbral_similitud: float = 0.0,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Recupera evidencia de la evaluación para múltiples subfactores del catálogo
        (o para todos los subfactores activos si subfactor_ids es None).
        """
        qs = Subfactor.objects.select_related('factor').filter(activo=True).order_by('subfactor_id')
        if subfactor_ids is not None:
            qs = qs.filter(subfactor_id__in=subfactor_ids)

        return {
            sf.subfactor_id: self.buscar_por_subfactor(
                evaluacion_id=evaluacion_id,
                subfactor_id=sf.subfactor_id,
                top_k=top_k,
                umbral_similitud=umbral_similitud,
            )
            for sf in qs
        }

    def estado_indexacion(self, evaluacion_id: int) -> Dict[str, int]:
        """Devuelve métricas de cobertura vectorial de una evaluación."""
        base_qs = FragmentoDocumento.objects.filter(documento__evaluacion_id=evaluacion_id)
        total = base_qs.count()
        indexados = base_qs.filter(embedding__isnull=False).count()
        pendientes = total - indexados
        porcentaje = round((indexados / total) * 100) if total > 0 else 0
        return {
            'total_fragmentos': total,
            'indexados': indexados,
            'pendientes': pendientes,
            'porcentaje': porcentaje,
        }