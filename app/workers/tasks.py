import logging
import asyncio
import tempfile
import time
from datetime import timedelta
from datetime import datetime

from celery.exceptions import Retry
from celery import shared_task
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.action import PendingAction, PendingActionStatus
from app.models.assistant import AIExtraction, AIExtractionStatus, AIItem
from app.models.capture import CaptureSession, SessionStatus
from app.models.pairing import DeviceUserBinding
from app.models.transcript import Transcript, TranscriptSegment
from app.services.action_detector import detect_communication_intents, draft_message
from app.services.assistant_llm import AssistantLLMError, extract_assistant_payload
from app.services.assistant_pipeline import AssistantPipelineError, prepare_extraction_record
from app.services.contact_resolver import resolve_contact
from app.services.entity_extraction import EntityExtractionError, extract_entities_from_transcript, persist_entities
from app.services.founder_intelligence import FounderIntelligenceError, process_founder_intelligence
from app.services.memory_card_summary import (
    MemoryCardSummaryError,
    build_memory_card_fallback,
    extract_memory_card_summary,
)
from app.services.memory_linking import suggest_memory_links_for_session
from app.services.transcriber import get_transcriber
from app.services.translation import needs_translation, translate_to_english, translate_segments
from app.services.embeddings import get_embeddings
from app.services.vector_store import get_vector_store
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


def _json_safe(value):
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


@shared_task(bind=True, name="app.workers.tasks.process_session_transcription")
def process_session_transcription(self, session_id: str) -> dict:
    db = SessionLocal()
    started = time.perf_counter()

    try:
        session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
        if not session:
            logger.error("Session not found for transcription: %s", session_id)
            return {"status": "error", "reason": "session_not_found"}

        session.status = SessionStatus.transcribing.value
        session.error_message = None
        db.commit()

        wav_bytes = session.audio_blob_wav
        if wav_bytes is None or len(wav_bytes) < 44:
            session.status = SessionStatus.failed.value
            session.error_message = "Missing direct WAV payload"
            db.commit()
            return {"status": "error", "reason": "missing_direct_wav"}

        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(wav_bytes)
            tmp.flush()
            transcriber = get_transcriber()
            result = transcriber.transcribe(tmp.name)

        # --- Translation: Convert non-English transcripts to English ---
        raw_full_text = result.get("full_text", "")
        detected_language = result.get("language")
        translated = False

        if needs_translation(detected_language, raw_full_text):
            logger.info(
                "Translating transcript to English: detected_language=%s text_len=%d session=%s",
                detected_language,
                len(raw_full_text),
                session_id,
            )
            english_full_text = translate_to_english(raw_full_text, detected_language)
            english_segments = translate_segments(result.get("segments", []), detected_language)
            translated = True
            logger.info(
                "Translation complete: original_len=%d english_len=%d session=%s",
                len(raw_full_text),
                len(english_full_text),
                session_id,
            )
        else:
            english_full_text = raw_full_text
            english_segments = result.get("segments", [])

        transcript = db.scalar(select(Transcript).where(Transcript.session_id == session.id))
        if not transcript:
            transcript = Transcript(
                session_id=session.id,
                model_name=result["model_name"],
                language="en" if translated else detected_language,
                full_text=english_full_text,
                original_text=raw_full_text if translated else None,
                original_language=detected_language if translated else None,
                duration_seconds=result.get("duration_seconds"),
            )
            db.add(transcript)
            db.flush()
        else:
            transcript.model_name = result["model_name"]
            transcript.language = "en" if translated else detected_language
            transcript.full_text = english_full_text
            transcript.original_text = raw_full_text if translated else None
            transcript.original_language = detected_language if translated else None
            transcript.duration_seconds = result.get("duration_seconds")
            db.execute(delete(TranscriptSegment).where(TranscriptSegment.transcript_id == transcript.id))

        segments_to_index = []
        for orig_seg, eng_seg in zip(result.get("segments", []), english_segments):
            segment_obj = TranscriptSegment(
                transcript_id=transcript.id,
                segment_index=eng_seg["segment_index"],
                start_seconds=eng_seg["start_seconds"],
                end_seconds=eng_seg["end_seconds"],
                text=eng_seg["text"],
                original_text=orig_seg["text"] if translated else None,
            )
            db.add(segment_obj)
            segments_to_index.append(segment_obj)

        db.flush() # Ensure segment_obj.id is populated

        # --- Vector Indexing ---
        try:
            user_id = db.scalar(
                select(DeviceUserBinding.user_id).where(
                    DeviceUserBinding.device_id == session.device_id,
                    DeviceUserBinding.is_active.is_(True),
                )
            )
            if user_id:
                vector_store = get_vector_store()
                for seg_obj in segments_to_index:
                    if not seg_obj.text.strip():
                        continue
                    try:
                        vector = get_embeddings(seg_obj.text)
                        vector_store.upsert_segment(
                            segment_id=seg_obj.id,
                            vector=vector,
                            metadata={
                                "user_id": user_id,
                                "session_id": session.id,
                                "transcript_id": transcript.id,
                                "text": seg_obj.text,
                                "start_seconds": seg_obj.start_seconds,
                                "created_at": transcript.created_at.isoformat(),
                            }
                        )
                    except Exception as embed_exc:
                        logger.warning(f"Failed to index segment {seg_obj.id}: {embed_exc}")
        except Exception as vector_exc:
            logger.warning(f"Vector indexing failed for session {session_id}: {vector_exc}")

        fallback_title, fallback_gist = build_memory_card_fallback(transcript.full_text)
        session.memory_title = fallback_title
        session.memory_gist = fallback_gist
        session.status = SessionStatus.done.value
        session.error_message = None
        session.finalized_at = session.finalized_at or utc_now()
        db.commit()

        if not transcript.full_text.strip():
            logger.info("Skipping AI extraction — transcript is empty for session=%s", session.id)
            session.status = SessionStatus.done.value
            db.commit()
            return {"status": "ok", "session_id": session.id, "extraction_skipped": True}

        try:
            _, _, extraction = prepare_extraction_record(db, session.id, force_reset=True)
            extraction.status = AIExtractionStatus.queued.value
            extraction.error_message = None
            db.commit()
            self.app.send_task("app.workers.tasks.process_session_ai_extraction", args=[session.id], queue="ai")
        except AssistantPipelineError as exc:
            db.rollback()
            logger.warning("AI extraction not queued for session=%s: %s", session.id, exc)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Failed to queue AI extraction for session=%s", session.id)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info("Transcription completed session=%s chunks=%s elapsed_ms=%s", session.id, session.total_chunks, elapsed_ms)

        return {"status": "ok", "session_id": session.id}

    except Retry:
        raise

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
        # Retry transient failures with exponential backoff.
        if session and self.request.retries < 5:
            retry_count = self.request.retries + 1
            countdown = min(300, 15 * (2 ** self.request.retries))
            session.status = SessionStatus.queued.value
            session.error_message = f"transcription_retry_{retry_count}: {str(exc)[:220]}"
            db.commit()
            logger.warning(
                "Transcription retry scheduled session=%s retry=%s countdown=%ss error=%s",
                session_id,
                retry_count,
                countdown,
                exc,
            )
            raise self.retry(exc=exc, countdown=countdown)

        if session:
            session.status = SessionStatus.failed.value
            session.error_message = str(exc)
            db.commit()
        logger.exception("Failed transcription for session %s", session_id)
        return {"status": "error", "reason": str(exc)}

    finally:
        db.close()


@shared_task(bind=True, name="app.workers.tasks.process_session_ai_extraction")
def process_session_ai_extraction(self, session_id: str) -> dict:
    db = SessionLocal()
    started = time.perf_counter()

    try:
        _, transcript, extraction = prepare_extraction_record(db, session_id)
        extraction.status = AIExtractionStatus.processing.value
        extraction.started_at = utc_now()
        extraction.completed_at = None
        extraction.error_message = None
        db.commit()

        payload = extract_assistant_payload(
            transcript_text=transcript.full_text,
            transcript_language=transcript.language,
        )

        db.execute(delete(AIItem).where(AIItem.extraction_id == extraction.id))
        created_at = utc_now()
        all_items = []
        for item in payload["plan_steps"] + payload["tasks"] + payload["reminders"]:
            all_items.append(
                AIItem(
                    extraction_id=extraction.id,
                    user_id=extraction.user_id,
                    session_id=extraction.session_id,
                    transcript_id=extraction.transcript_id,
                    item_type=item["item_type"],
                    title=item["title"],
                    details=item["details"],
                    due_at=item["due_at"],
                    timezone=item["timezone"],
                    priority=item["priority"],
                    status=item["status"],
                    source_segment_start_seconds=item["source_segment_start_seconds"],
                    source_segment_end_seconds=item["source_segment_end_seconds"],
                    completed_at=created_at if item["status"] == "done" else None,
                )
            )

        for row in all_items:
            db.add(row)

        extraction.intent = payload["intent"]
        extraction.intent_confidence = payload["intent_confidence"]
        extraction.summary = payload["summary"]
        extraction.plan_json = _json_safe(payload["plan_steps"])
        extraction.raw_json = payload["raw_json"]
        extraction.model_name = payload["model_name"]
        extraction.status = AIExtractionStatus.done.value
        extraction.error_message = None
        extraction.completed_at = utc_now()
        db.commit()

        session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
        if session is not None:
            try:
                card = extract_memory_card_summary(
                    transcript_text=transcript.full_text,
                    transcript_language=transcript.language,
                    assistant_summary=payload["summary"],
                )
                session.memory_title = card["memory_title"]
                session.memory_gist = card["memory_gist"]
            except MemoryCardSummaryError as exc:
                fallback_title, fallback_gist = build_memory_card_fallback(
                    transcript.full_text,
                    assistant_summary=payload["summary"],
                )
                session.memory_title = fallback_title
                session.memory_gist = fallback_gist
                logger.warning(
                    "Memory card summary fallback used for session=%s: %s",
                    session_id,
                    exc,
                )
            db.commit()

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "AI extraction completed session=%s transcript=%s extraction=%s items=%s elapsed_ms=%s",
            session_id,
            extraction.transcript_id,
            extraction.id,
            len(all_items),
            elapsed_ms,
        )

        # --- Entity Graph Extraction ---
        try:
            raw_entities = extract_entities_from_transcript(
                transcript_text=transcript.full_text,
                transcript_language=transcript.language,
            )
            if raw_entities:
                entity_count = persist_entities(
                    db=db,
                    user_id=extraction.user_id,
                    session_id=extraction.session_id,
                    extraction_id=extraction.id,
                    entities=raw_entities,
                )
                logger.info(
                    "Entity extraction completed session=%s entities_found=%s mentions_created=%s",
                    session_id,
                    len(raw_entities),
                    entity_count,
                )
        except (EntityExtractionError, Exception) as entity_exc:  # noqa: BLE001
            logger.warning(
                "Entity extraction failed for session=%s (non-fatal): %s",
                session_id,
                entity_exc,
            )

        try:
            self.app.send_task("app.workers.tasks.process_session_founder_intelligence", args=[session_id], queue="ai")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to queue founder intelligence for session=%s", session_id)

        try:
            self.app.send_task(
                "app.workers.tasks.process_session_actions",
                args=[session_id, str(extraction.user_id)],
                queue="ai",
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to queue action detection for session=%s", session_id)

        return {"status": "ok", "session_id": session_id, "extraction_id": extraction.id}

    except Retry:
        raise

    except AssistantLLMError as exc:
        if "empty" in str(exc).lower():
            logger.warning("Skipping AI extraction — transcript empty, no retry. session=%s", session_id)
            extraction = db.scalar(select(AIExtraction).where(AIExtraction.session_id == session_id))
            if extraction:
                extraction.status = AIExtractionStatus.done.value
                extraction.error_message = "No speech detected (empty transcript)."
                extraction.completed_at = utc_now()
                db.commit()
            return {"status": "skipped", "reason": "empty_transcript"}
        raise exc  # Will be caught by generic Exception block for normal retry logic

    except AssistantPipelineError as exc:
        db.rollback()
        logger.warning("AI extraction skipped session=%s reason=%s", session_id, exc)
        return {"status": "error", "reason": str(exc)}

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        extraction = db.scalar(select(AIExtraction).where(AIExtraction.session_id == session_id))
        if extraction and self.request.retries < 4:
            retry_count = self.request.retries + 1
            countdown = min(300, 20 * (2 ** self.request.retries))
            extraction.status = AIExtractionStatus.queued.value
            extraction.error_message = f"ai_retry_{retry_count}: {str(exc)[:220]}"
            db.commit()
            logger.warning(
                "AI extraction retry scheduled session=%s extraction=%s retry=%s countdown=%ss error=%s",
                session_id,
                extraction.id,
                retry_count,
                countdown,
                exc,
            )
            raise self.retry(exc=exc, countdown=countdown)

        if extraction:
            extraction.status = AIExtractionStatus.failed.value
            extraction.error_message = str(exc)
            extraction.completed_at = utc_now()
            db.commit()

        if isinstance(exc, AssistantLLMError):
            logger.warning("AI extraction failed session=%s reason=%s", session_id, exc)
        else:
            logger.exception("AI extraction failed session=%s", session_id)
        return {"status": "error", "reason": str(exc)}

    finally:
        db.close()


@shared_task(bind=True, name="app.workers.tasks.process_session_actions")
def process_session_actions(self, session_id: str, user_id: str) -> dict:
    db = SessionLocal()
    started = time.perf_counter()

    try:
        transcript = db.scalar(select(Transcript).where(Transcript.session_id == session_id))
        if not transcript or not transcript.full_text.strip():
            logger.info("Action detection skipped session=%s reason=missing_transcript", session_id)
            return {"status": "ok", "session_id": session_id, "actions_detected": 0}

        intents = asyncio.run(detect_communication_intents(transcript.full_text))
        created = 0

        for intent in intents:
            confidence = float(intent.get("confidence") or 0.0)
            if confidence < 0.5:
                continue

            recipient_name = str(intent.get("recipient_name") or "").strip()
            original_snippet = str(intent.get("original_snippet") or "").strip() or None
            action_type = str(intent.get("preferred_channel") or intent.get("action_type") or "whatsapp").strip()
            if not recipient_name:
                continue

            existing = db.scalar(
                select(PendingAction).where(
                    PendingAction.user_id == user_id,
                    PendingAction.session_id == session_id,
                    PendingAction.action_type == action_type,
                    PendingAction.recipient_name == recipient_name,
                    PendingAction.original_transcript_snippet == original_snippet,
                )
            )
            if existing:
                continue

            contact, resolved = asyncio.run(resolve_contact(user_id, recipient_name, db))
            draft = asyncio.run(draft_message(intent))

            action = PendingAction(
                user_id=user_id,
                session_id=session_id,
                action_type=action_type,
                status=PendingActionStatus.pending.value,
                contact_id=contact.id if contact else None,
                recipient_name=contact.name if contact else recipient_name,
                recipient_phone=(contact.whatsapp_number or contact.phone) if contact else None,
                recipient_email=contact.email if contact else None,
                contact_resolved=resolved,
                draft_subject=draft.get("subject"),
                draft_body=str(draft.get("body") or intent.get("message_context") or "").strip(),
                original_transcript_snippet=original_snippet,
                confidence_score=confidence,
            )
            db.add(action)
            created += 1

        db.commit()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Action detection completed session=%s actions_detected=%s elapsed_ms=%s",
            session_id,
            created,
            elapsed_ms,
        )
        return {"status": "ok", "session_id": session_id, "actions_detected": created}

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Action detection failed session=%s", session_id)
        return {"status": "error", "reason": str(exc), "session_id": session_id}

    finally:
        db.close()


@shared_task(bind=True, name="app.workers.tasks.process_session_founder_intelligence")
def process_session_founder_intelligence_task(self, session_id: str) -> dict:
    db = SessionLocal()
    started = time.perf_counter()
    try:
        result = process_founder_intelligence(db, session_id)
        session = db.scalar(select(CaptureSession).where(CaptureSession.id == session_id))
        if session:
            user_id = db.scalar(
                select(DeviceUserBinding.user_id).where(
                    DeviceUserBinding.device_id == session.device_id,
                    DeviceUserBinding.is_active.is_(True),
                )
            )
            if user_id:
                link_result = suggest_memory_links_for_session(db, user_id=user_id, session_id=session_id)
                result["link_suggestions"] = link_result
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "Founder intelligence completed session=%s idea_id=%s signals=%s actions=%s links=%s elapsed_ms=%s",
            session_id,
            result.get("idea_id"),
            result.get("signal_count"),
            result.get("action_count"),
            result.get("link_suggestions"),
            elapsed_ms,
        )
        return {"status": "ok", "session_id": session_id, **result}
    except FounderIntelligenceError as exc:
        db.rollback()
        logger.warning("Founder intelligence skipped session=%s reason=%s", session_id, exc)
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Founder intelligence failed session=%s", session_id)
        if self.request.retries < 3:
            countdown = min(300, 30 * (2 ** self.request.retries))
            raise self.retry(exc=exc, countdown=countdown)
        return {"status": "error", "reason": str(exc)}
    finally:
        db.close()


@shared_task(bind=True, name="app.workers.tasks.recover_stuck_transcriptions")
def recover_stuck_transcriptions(self, limit: int = 100) -> dict:
    """
    Requeue stale transcribing sessions and all queued sessions.
    Safe to run multiple times.
    """
    db = SessionLocal()
    try:
        now = utc_now()
        stale_cutoff = now - timedelta(minutes=5)
        clamped_limit = max(1, min(limit, 500))

        stale_sessions = db.scalars(
            select(CaptureSession).where(
                CaptureSession.status == SessionStatus.transcribing.value,
                CaptureSession.finalized_at.is_not(None),
                CaptureSession.finalized_at < stale_cutoff,
            ).limit(clamped_limit)
        ).all()

        for session in stale_sessions:
            session.status = SessionStatus.queued.value
            session.error_message = "recovered_from_stale_transcribing"

        queued_ids = db.scalars(
            select(CaptureSession.id).where(CaptureSession.status == SessionStatus.queued.value).limit(clamped_limit)
        ).all()
        db.commit()

        enqueued = 0
        for sid in queued_ids:
            self.app.send_task("app.workers.tasks.process_session_transcription", args=[sid], queue="transcription")
            enqueued += 1

        ai_stale_cutoff = now - timedelta(minutes=5)
        stale_ai = db.scalars(
            select(AIExtraction).where(
                AIExtraction.status == AIExtractionStatus.processing.value,
                AIExtraction.started_at.is_not(None),
                AIExtraction.started_at < ai_stale_cutoff,
            ).limit(clamped_limit)
        ).all()
        for extraction in stale_ai:
            extraction.status = AIExtractionStatus.queued.value
            extraction.error_message = "recovered_from_stale_processing"

        queued_ai = db.scalars(
            select(AIExtraction).where(AIExtraction.status == AIExtractionStatus.queued.value).limit(clamped_limit)
        ).all()
        db.commit()

        enqueued_ai = 0
        for extraction in queued_ai:
            self.app.send_task("app.workers.tasks.process_session_ai_extraction", args=[extraction.session_id], queue="ai")
            enqueued_ai += 1

        return {
            "status": "ok",
            "stale_recovered": len(stale_sessions),
            "enqueued": enqueued,
            "ai_stale_recovered": len(stale_ai),
            "ai_enqueued": enqueued_ai,
        }
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Failed recovering stuck transcriptions")
        return {"status": "error", "reason": str(exc)}
    finally:
        db.close()
