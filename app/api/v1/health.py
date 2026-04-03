from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.assistant import AIExtraction
from app.schemas.assistant import AIPipelineMetricsResponse
from app.utils.time import utc_now

router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@router.get("/health/ai-metrics", response_model=AIPipelineMetricsResponse)
def ai_metrics(db: Session = Depends(get_db)) -> AIPipelineMetricsResponse:
    counts = dict(
        db.execute(
            select(AIExtraction.status, func.count(AIExtraction.id)).group_by(AIExtraction.status)
        ).all()
    )
    status_counts = {
        "queued": int(counts.get("queued", 0)),
        "processing": int(counts.get("processing", 0)),
        "done": int(counts.get("done", 0)),
        "failed": int(counts.get("failed", 0)),
    }

    done_rows = db.scalars(
        select(AIExtraction)
        .where(AIExtraction.status == "done", AIExtraction.started_at.is_not(None), AIExtraction.completed_at.is_not(None))
        .order_by(AIExtraction.completed_at.desc())
        .limit(200)
    ).all()
    avg_ms: int | None = None
    if done_rows:
        total_ms = 0
        samples = 0
        for row in done_rows:
            if row.started_at and row.completed_at:
                total_ms += int((row.completed_at - row.started_at).total_seconds() * 1000)
                samples += 1
        if samples > 0:
            avg_ms = int(total_ms / samples)

    last_failed = db.scalar(
        select(AIExtraction)
        .where(AIExtraction.status == "failed")
        .order_by(AIExtraction.updated_at.desc())
        .limit(1)
    )
    last_error = last_failed.error_message if last_failed else None

    return AIPipelineMetricsResponse(
        status_counts=status_counts,
        avg_done_latency_ms=avg_ms,
        last_error=last_error,
        updated_at=utc_now(),
    )
