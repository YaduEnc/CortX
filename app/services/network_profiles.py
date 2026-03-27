from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import redis

from app.core.config import get_settings

NETWORK_PROFILE_TTL_SECONDS = 24 * 60 * 60


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _profile_key(device_id: str) -> str:
    return f"device:network_profile:{device_id}"


def queue_network_profile(device_id: str, ssid: str, password: str, source: str) -> None:
    payload = json.dumps(
        {
            "ssid": ssid,
            "password": password,
            "source": source,
        }
    )
    get_redis_client().set(_profile_key(device_id), payload, ex=NETWORK_PROFILE_TTL_SECONDS)


def consume_network_profile(device_id: str) -> dict[str, Any] | None:
    client = get_redis_client()
    key = _profile_key(device_id)
    value = client.getdel(key)
    if not value:
        return None

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed
