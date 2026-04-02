#!/usr/bin/env python3
"""
SecondMind Supabase AI Worker (LM Studio)

Polls ai_pipeline_jobs, extracts structured memory from transcript text,
and writes memory_items/entities links back into Supabase.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from supabase import Client, create_client


ALLOWED_ENTITY_TYPES = {"person", "project", "org", "place", "topic", "time"}
ALLOWED_ITEM_TYPES = ("task", "idea", "decision", "reminder")


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_service_role_key: str
    lm_studio_base_url: str
    lm_studio_model: str
    poll_seconds: float
    request_timeout_seconds: int
    max_items_per_type: int


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def load_settings() -> Settings:
    return Settings(
        supabase_url=_required_env("SUPABASE_URL"),
        supabase_service_role_key=_required_env("SUPABASE_SERVICE_ROLE_KEY"),
        lm_studio_base_url=os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").strip().rstrip("/"),
        lm_studio_model=os.getenv("LM_STUDIO_MODEL", "qwen2.5-7b-instruct").strip(),
        poll_seconds=float(os.getenv("AI_PIPELINE_POLL_SECONDS", "2")),
        request_timeout_seconds=int(os.getenv("AI_PIPELINE_REQUEST_TIMEOUT_SECONDS", "180")),
        max_items_per_type=int(os.getenv("AI_PIPELINE_MAX_ITEMS_PER_TYPE", "12")),
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return 0.0
    if v > 1:
        return 1.0
    return round(v, 3)


def clamp_priority(value: Any) -> int | None:
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    if v < 1:
        return 1
    if v > 5:
        return 5
    return v


def normalize_entity_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


def extract_json_block(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", stripped)
        stripped = re.sub(r"\n```$", "", stripped)

    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    first = stripped.find("{")
    last = stripped.rfind("}")
    if first >= 0 and last > first:
        candidate = stripped[first : last + 1]
        obj = json.loads(candidate)
        if isinstance(obj, dict):
            return obj

    raise ValueError("Model output is not valid JSON object")


def normalize_item(raw: dict[str, Any], item_type: str) -> dict[str, Any] | None:
    title = str(raw.get("title") or "").strip()
    details = str(raw.get("details") or "").strip() or None
    if not title:
        if details:
            title = details[:100]
        else:
            return None

    return {
        "item_type": item_type,
        "title": title[:255],
        "details": details,
        "priority": clamp_priority(raw.get("priority")) if item_type == "task" else None,
        "due_at": raw.get("due_at"),
        "happened_at": raw.get("happened_at"),
        "confidence": clamp_confidence(raw.get("confidence")),
        "source_quote": (str(raw.get("source_quote") or "").strip() or None),
        "source_start_seconds": raw.get("source_start_seconds"),
        "source_end_seconds": raw.get("source_end_seconds"),
        "entities": raw.get("entities") if isinstance(raw.get("entities"), list) else [],
    }


def normalize_payload(payload: dict[str, Any], max_items_per_type: int) -> dict[str, Any]:
    normalized: dict[str, Any] = {k: [] for k in ALLOWED_ITEM_TYPES}
    normalized["entities"] = []

    for item_type in ALLOWED_ITEM_TYPES:
        raw_items = payload.get(item_type) or []
        if not isinstance(raw_items, list):
            continue
        for raw in raw_items[: max_items_per_type]:
            if not isinstance(raw, dict):
                continue
            item = normalize_item(raw, item_type)
            if item:
                normalized[item_type].append(item)

    raw_entities = payload.get("entities") or []
    if isinstance(raw_entities, list):
        for raw in raw_entities[: max_items_per_type * 3]:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            et = str(raw.get("entity_type") or "").strip().lower()
            if not name or et not in ALLOWED_ENTITY_TYPES:
                continue
            normalized["entities"].append(
                {
                    "name": name[:255],
                    "normalized_name": normalize_entity_name(name),
                    "entity_type": et,
                }
            )

    return normalized


def build_extraction_messages(transcript_text: str) -> list[dict[str, str]]:
    schema_hint = {
        "tasks": [
            {
                "title": "string",
                "details": "string|null",
                "priority": "1-5|null",
                "due_at": "ISO8601|null",
                "confidence": "0..1",
                "source_quote": "string|null",
                "entities": [{"name": "string", "entity_type": "person|project|org|place|topic|time"}],
            }
        ],
        "ideas": [
            {
                "title": "string",
                "details": "string|null",
                "confidence": "0..1",
                "source_quote": "string|null",
                "entities": [{"name": "string", "entity_type": "person|project|org|place|topic|time"}],
            }
        ],
        "decisions": [
            {
                "title": "string",
                "details": "string|null",
                "confidence": "0..1",
                "source_quote": "string|null",
                "entities": [{"name": "string", "entity_type": "person|project|org|place|topic|time"}],
            }
        ],
        "reminders": [
            {
                "title": "string",
                "details": "string|null",
                "due_at": "ISO8601|null",
                "confidence": "0..1",
                "source_quote": "string|null",
                "entities": [{"name": "string", "entity_type": "person|project|org|place|topic|time"}],
            }
        ],
        "entities": [{"name": "string", "entity_type": "person|project|org|place|topic|time"}],
    }

    system = (
        "You are an extraction engine. Return ONLY valid JSON. "
        "Do not include markdown fences. "
        "Do not hallucinate facts not present in transcript. "
        "Support multilingual/Hinglish transcripts."
    )
    user = (
        "Extract tasks, ideas, decisions, reminders, and entities from the transcript.\n"
        "Use this JSON schema shape exactly:\n"
        f"{json.dumps(schema_hint, ensure_ascii=False)}\n\n"
        "Transcript:\n"
        f"{transcript_text}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_lm_studio(settings: Settings, transcript_text: str) -> dict[str, Any]:
    url = f"{settings.lm_studio_base_url}/chat/completions"
    payload = {
        "model": settings.lm_studio_model,
        "temperature": 0.1,
        "messages": build_extraction_messages(transcript_text),
    }

    response = requests.post(url, json=payload, timeout=settings.request_timeout_seconds)
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("LM Studio returned no choices")

    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LM Studio returned empty content")

    return extract_json_block(content)


def add_log(supabase: Client, transcript_id: int, stage: str, level: str, message: str, payload: dict[str, Any] | None = None) -> None:
    supabase.table("ai_pipeline_logs").insert(
        {
            "transcript_id": transcript_id,
            "stage": stage,
            "level": level,
            "message": message,
            "payload": payload,
            "created_at": utc_now_iso(),
        }
    ).execute()


def fetch_transcript(supabase: Client, transcript_id: int) -> dict[str, Any]:
    res = (
        supabase.table("transcripts")
        .select("id,user_id,device_code,audio_file,transcript,created_at")
        .eq("id", transcript_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise ValueError(f"Transcript not found: {transcript_id}")
    return rows[0]


def get_or_create_entity(supabase: Client, user_id: str, name: str, entity_type: str) -> str:
    normalized_name = normalize_entity_name(name)
    if not normalized_name:
        raise ValueError("Cannot create empty entity name")

    existing = (
        supabase.table("entities")
        .select("id")
        .eq("user_id", user_id)
        .eq("normalized_name", normalized_name)
        .eq("entity_type", entity_type)
        .limit(1)
        .execute()
    )
    rows = existing.data or []
    if rows:
        return rows[0]["id"]

    try:
        inserted = (
            supabase.table("entities")
            .insert(
                {
                    "user_id": user_id,
                    "name": name[:255],
                    "normalized_name": normalized_name,
                    "entity_type": entity_type,
                }
            )
            .execute()
        )
        return inserted.data[0]["id"]
    except Exception:
        fallback = (
            supabase.table("entities")
            .select("id")
            .eq("user_id", user_id)
            .eq("normalized_name", normalized_name)
            .eq("entity_type", entity_type)
            .limit(1)
            .execute()
        )
        rows = fallback.data or []
        if not rows:
            raise
        return rows[0]["id"]


def save_memory(supabase: Client, transcript: dict[str, Any], normalized_payload: dict[str, Any]) -> dict[str, int]:
    transcript_id = int(transcript["id"])
    user_id = str(transcript.get("user_id") or "").strip()
    device_code = str(transcript.get("device_code") or "").strip() or None

    if not user_id:
        raise ValueError("transcripts.user_id is required")

    supabase.rpc("purge_memory_for_transcript", {"p_transcript_id": transcript_id}).execute()

    global_entity_ids: dict[tuple[str, str], str] = {}
    for entity in normalized_payload["entities"]:
        key = (entity["normalized_name"], entity["entity_type"])
        global_entity_ids[key] = get_or_create_entity(supabase, user_id, entity["name"], entity["entity_type"])

    inserted_count = 0
    for item_type in ALLOWED_ITEM_TYPES:
        items = normalized_payload[item_type]
        for item in items:
            insert_payload = {
                "transcript_id": transcript_id,
                "user_id": user_id,
                "device_code": device_code,
                "item_type": item_type,
                "title": item["title"],
                "details": item["details"],
                "priority": item["priority"],
                "due_at": item["due_at"],
                "happened_at": item["happened_at"],
                "status": "open",
                "confidence": item["confidence"],
                "source_quote": item["source_quote"],
                "source_start_seconds": item["source_start_seconds"],
                "source_end_seconds": item["source_end_seconds"],
            }
            row = supabase.table("memory_items").insert(insert_payload).execute().data[0]
            memory_item_id = row["id"]
            inserted_count += 1

            per_item_entities: set[tuple[str, str]] = set(global_entity_ids.keys())
            for e in item["entities"]:
                name = str(e.get("name") or "").strip()
                entity_type = str(e.get("entity_type") or "").strip().lower()
                if not name or entity_type not in ALLOWED_ENTITY_TYPES:
                    continue
                per_item_entities.add((normalize_entity_name(name), entity_type))
                if (normalize_entity_name(name), entity_type) not in global_entity_ids:
                    global_entity_ids[(normalize_entity_name(name), entity_type)] = get_or_create_entity(
                        supabase, user_id, name, entity_type
                    )

            for norm_name, entity_type in per_item_entities:
                entity_id = global_entity_ids.get((norm_name, entity_type))
                if not entity_id:
                    continue
                supabase.table("memory_item_entities").upsert(
                    {
                        "memory_item_id": memory_item_id,
                        "entity_id": entity_id,
                        "role": "mentioned",
                    },
                    on_conflict="memory_item_id,entity_id,role",
                ).execute()

    return {"memory_items_inserted": inserted_count, "entities_count": len(global_entity_ids)}


def claim_one_job(supabase: Client) -> dict[str, Any] | None:
    res = supabase.rpc("claim_ai_pipeline_job", {}).execute()
    rows = res.data or []
    if not rows:
        return None
    return rows[0]


def complete_job(supabase: Client, job_id: str, success: bool, error_text: str | None = None) -> None:
    supabase.rpc(
        "complete_ai_pipeline_job",
        {"p_job_id": job_id, "p_success": success, "p_error": error_text},
    ).execute()


def process_job(supabase: Client, settings: Settings, job: dict[str, Any]) -> None:
    job_id = job["id"]
    transcript_id = int(job["transcript_id"])
    add_log(supabase, transcript_id, "claim", "info", f"claimed job {job_id}", {"attempts": job.get("attempts")})

    transcript = fetch_transcript(supabase, transcript_id)
    transcript_text = str(transcript.get("transcript") or "").strip()
    if not transcript_text:
        raise ValueError("Transcript text is empty")

    add_log(supabase, transcript_id, "extract", "info", "sending transcript to LM Studio")
    extracted = call_lm_studio(settings, transcript_text)
    normalized = normalize_payload(extracted, settings.max_items_per_type)

    add_log(
        supabase,
        transcript_id,
        "extract",
        "info",
        "LM Studio extraction complete",
        {
            "tasks": len(normalized["task"]),
            "ideas": len(normalized["idea"]),
            "decisions": len(normalized["decision"]),
            "reminders": len(normalized["reminder"]),
            "entities": len(normalized["entities"]),
        },
    )

    stats = save_memory(supabase, transcript, normalized)
    add_log(supabase, transcript_id, "save", "info", "memory write complete", stats)
    complete_job(supabase, job_id, True, None)


def run_loop() -> None:
    settings = load_settings()
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)

    print("[AI_WORKER] started")
    print(f"[AI_WORKER] lm_studio={settings.lm_studio_base_url} model={settings.lm_studio_model}")
    print(f"[AI_WORKER] poll_seconds={settings.poll_seconds}")
    sys.stdout.flush()

    while True:
        try:
            job = claim_one_job(supabase)
            if not job:
                time.sleep(settings.poll_seconds)
                continue

            try:
                process_job(supabase, settings, job)
            except Exception as job_exc:  # noqa: BLE001
                transcript_id = int(job.get("transcript_id") or 0)
                add_log(
                    supabase,
                    transcript_id,
                    "error",
                    "error",
                    "job processing failed",
                    {"error": str(job_exc)},
                )
                complete_job(supabase, job["id"], False, str(job_exc))

        except KeyboardInterrupt:
            print("\n[AI_WORKER] stopped by user")
            break
        except Exception as loop_exc:  # noqa: BLE001
            print(f"[AI_WORKER] loop error: {loop_exc}")
            sys.stdout.flush()
            time.sleep(max(settings.poll_seconds, 2))


if __name__ == "__main__":
    run_loop()
