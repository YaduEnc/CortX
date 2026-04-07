from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.capture import CaptureSession
from app.models.transcript import Transcript
from app.services.vector_store import get_vector_store
from app.services.embeddings import get_embeddings
from app.services.assistant_llm import get_settings, requests, AssistantLLMError

def query_memories_semantically(
    db: Session,
    user_id: str,
    query: str,
    limit: int = 5
) -> Dict[str, Any]:
    # 1. Generate embedding for the query
    query_vector = get_embeddings(query)
    
    # 2. Search Qdrant for relevant segments
    vector_store = get_vector_store()
    hits = vector_store.search(query_vector, user_id=user_id, limit=limit)
    
    if not hits:
        return {
            "answer": "I couldn't find any relevant memories to answer that question.",
            "sources": []
        }
        
    # 3. Context Preparation
    context_parts = []
    seen_sessions = set()
    sources = []
    
    for hit in hits:
        payload = hit["payload"]
        sid = payload["session_id"]
        context_parts.append(f"Source: {payload.get('text', '')}")
        
        if sid not in seen_sessions:
            seen_sessions.add(sid)
            sources.append({
                "session_id": sid,
                "text": payload.get("text"),
                "created_at": payload.get("created_at")
            })
            
    context_text = "\n".join(context_parts)
    
    # 4. LLM Formulation (RAG)
    settings = get_settings()
    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    
    system_prompt = (
        "You are CortX, a founder's second mind. Use the provided conversation snippets to answer the user's question accurately. "
        "If the answer isn't in the snippets, say you don't know based on the recorded memories. "
        "Answer in a concise and professional tone. "
        "Format the answer in English."
    )
    
    user_prompt = (
        f"Context from memories:\n{context_text}\n\n"
        f"User Question: {query}\n\n"
        "Answer based ONLY on the context above:"
    )
    
    try:
        response = requests.post(
            url,
            json={
                "model": settings.lmstudio_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1
            },
            timeout=settings.lmstudio_timeout_seconds
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        answer = f"I found some relevant snippets, but I couldn't formulate a summary right now. Here are the matches: \n" + "\n".join([s["text"] for s in sources[:2]])
        
    return {
        "answer": answer.strip(),
        "sources": sources
    }
