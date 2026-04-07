import requests
from typing import List
from app.core.config import get_settings

class EmbeddingServiceError(RuntimeError):
    pass

def get_embeddings(text: str) -> List[float]:
    settings = get_settings()
    url = f"{settings.lmstudio_base_url.rstrip('/')}/embeddings"
    
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"
        
    payload = {
        "model": settings.lmstudio_model,
        "input": text
    }
    
    try:
        response = requests.post(
            url, 
            headers=headers, 
            json=payload, 
            timeout=settings.lmstudio_timeout_seconds
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
    except Exception as exc:
        raise EmbeddingServiceError(f"Failed to fetch embeddings from LM Studio: {exc}") from exc
