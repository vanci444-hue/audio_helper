import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from constants import AUDIO_TTL
from schemas import AppError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredAudio:
    audio_id: str
    created_at: datetime
    audio_path: Path
    meta_path: Path
    size_bytes: int
    duration_seconds: float
    codec: str
    container: str


def save_audio(
    data: bytes,
    *,
    duration_seconds: float,
    codec: str,
    container: str,
    original_filename: str | None,
) -> StoredAudio:
    storage_dir = Path(settings.storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    audio_id = f"aud_{uuid.uuid4().hex}"
    created_at = datetime.now(timezone.utc)
    audio_path = storage_dir / f"{audio_id}.webm"
    meta_path = storage_dir / f"{audio_id}.json"
    audio_path.write_bytes(data)
    metadata = {
        "audio_id": audio_id,
        "created_at": created_at.isoformat(),
        "original_filename": original_filename or "",
        "codec": codec,
        "container": container,
        "duration_seconds": duration_seconds,
        "size_bytes": len(data),
    }
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("stored audio_id=%s bytes=%s duration_s=%.3f", audio_id, len(data), duration_seconds)
    return StoredAudio(
        audio_id=audio_id,
        created_at=created_at,
        audio_path=audio_path,
        meta_path=meta_path,
        size_bytes=len(data),
        duration_seconds=duration_seconds,
        codec=codec,
        container=container,
    )


def read_audio_record(audio_id: str, *, stage: str) -> StoredAudio:
    """Load metadata and check 24h TTL. Not exposed as an HTTP route this round."""
    not_found = AppError(404, "AUDIO_NOT_FOUND", "录音不存在或已过期，请重新上传。", stage)
    if not _safe_audio_id(audio_id):
        raise not_found
    storage_dir = Path(settings.storage_dir)
    meta_path = storage_dir / f"{audio_id}.json"
    audio_path = storage_dir / f"{audio_id}.webm"
    if not meta_path.is_file() or not audio_path.is_file():
        raise not_found
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(metadata["created_at"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(404, "AUDIO_NOT_FOUND", "录音不存在或已过期，请重新上传。", stage) from exc
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created_at > AUDIO_TTL:
        raise AppError(404, "AUDIO_NOT_FOUND", "录音不存在或已过期，请重新上传。", stage)
    return StoredAudio(
        audio_id=audio_id,
        created_at=created_at,
        audio_path=audio_path,
        meta_path=meta_path,
        size_bytes=int(metadata.get("size_bytes") or audio_path.stat().st_size),
        duration_seconds=float(metadata.get("duration_seconds") or 0),
        codec=str(metadata.get("codec") or ""),
        container=str(metadata.get("container") or ""),
    )


def _safe_audio_id(audio_id: str) -> bool:
    return audio_id.startswith("aud_") and audio_id[4:].isalnum()
