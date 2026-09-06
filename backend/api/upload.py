import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Request, UploadFile

from constants import MAX_AUDIO_BYTES
from schemas import AppError, UploadData, UploadResponse
from services.audio_probe import probe_audio_file
from services.storage import save_audio

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload(
    request: Request,
    file: UploadFile = File(..., description="录音文件，字段名必须为 file"),
) -> UploadResponse:
    data = await _read_limited(file)
    if not data:
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "录音格式不受支持，请使用 WebM/Opus 录音，或更换 Chrome、Edge 后重试。",
            "upload",
        )

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        probe = probe_audio_file(Path(tmp.name))

    stored = save_audio(
        data,
        duration_seconds=probe.duration_seconds,
        codec=probe.codec,
        container=probe.container,
        original_filename=file.filename,
    )
    logger.info("upload ok request_id=%s audio_id=%s", request.state.request_id, stored.audio_id)
    return UploadResponse(
        request_id=request.state.request_id,
        data=UploadData(audio_id=stored.audio_id),
    )


async def _read_limited(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_AUDIO_BYTES:
            raise AppError(
                413,
                "FILE_TOO_LARGE",
                "录音文件超过 5MB，请缩短录音后重试。",
                "upload",
            )
        chunks.append(chunk)
    return b"".join(chunks)
