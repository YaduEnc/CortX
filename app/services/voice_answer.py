from __future__ import annotations

import logging
from typing import Any

import requests

from app.core.config import get_settings
from app.services.assistant_llm import _content_to_text

logger = logging.getLogger(__name__)


VOICE_ANSWER_SYSTEM_PROMPT = (
    "You are SecondMind, a personal cognitive assistant. "
    "The user asked a question by voice. You have retrieved relevant memory context. "
    "Rewrite the answer as a natural, concise spoken response -- 2 to 4 sentences max. "
    "Do not use bullet points, markdown, or lists. "
    "Speak directly to the user. Start with their answer immediately."
)


def refine_spoken_answer(query_text: str, raw_answer: str) -> str:
    settings = get_settings()
    answer = raw_answer.strip()
    if not answer:
        return "I could not find a clear answer in your memories."

    url = settings.lmstudio_base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.lmstudio_api_key:
        headers["Authorization"] = f"Bearer {settings.lmstudio_api_key}"

    payload: dict[str, Any] = {
        "model": settings.lmstudio_model,
        "temperature": settings.lmstudio_temperature,
        "messages": [
            {"role": "system", "content": VOICE_ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Voice question:\n"
                    f"{query_text}\n\n"
                    "Retrieved memory answer:\n"
                    f"{answer}\n\n"
                    "Rewrite this for spoken playback."
                ),
            },
        ],
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=settings.lmstudio_timeout_seconds)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("LM Studio returned no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise ValueError("LM Studio response missing message")
        refined = _content_to_text(message.get("content")).strip()
        return refined or answer
    except Exception as exc:  # noqa: BLE001
        logger.warning("Voice answer refinement failed; using raw memory answer: %s", exc)
        return answer
