import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import get_settings
from app.services.embeddings import get_embeddings

logger = logging.getLogger(__name__)

COLLECTION_NAME = "memories"

class VectorStoreError(RuntimeError):
    pass

class VectorStore:
    def __init__(self):
        settings = get_settings()
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
        )
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == COLLECTION_NAME for c in collections)
            
            if not exists:
                # We need to know the dimension. Let's get a sample embedding.
                sample_vec = get_embeddings("sample text")
                dimension = len(sample_vec)
                
                logger.info(f"Creating Qdrant collection '{COLLECTION_NAME}' with dimension {dimension}")
                self.client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=models.VectorParams(
                        size=dimension, 
                        distance=models.Distance.COSINE
                    ),
                )
        except Exception as exc:
            logger.error(f"Failed to ensure Qdrant collection: {exc}")
            # Non-fatal during initialization if Qdrant is still starting up
            pass

    def upsert_segment(
        self, 
        segment_id: str, 
        vector: List[float], 
        metadata: Dict[str, Any]
    ):
        try:
            self.client.upsert(
                collection_name=COLLECTION_NAME,
                points=[
                    models.PointStruct(
                        id=segment_id,
                        vector=vector,
                        payload=metadata
                    )
                ]
            )
        except Exception as exc:
            raise VectorStoreError(f"Failed to upsert to Qdrant: {exc}") from exc

    def search(
        self, 
        query_vector: List[float], 
        user_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        try:
            results = self.client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id)
                        )
                    ]
                ),
                limit=limit,
                with_payload=True
            )
            return [
                {
                    "id": hit.id,
                    "score": hit.score,
                    "payload": hit.payload
                }
                for hit in results
            ]
        except Exception as exc:
            raise VectorStoreError(f"Failed to search Qdrant: {exc}") from exc

_vector_store = None

def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store
