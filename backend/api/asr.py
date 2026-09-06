import logging

from fastapi import APIRouter, Request

from schemas import AsrData, AsrRequest, AsrResponse
from services.asr import transcribe_audio
from services.storage import read_audio_record

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/asr", response_model=AsrResponse)
def asr(request: Request, body: AsrRequest) -> AsrResponse:
    record = read_audio_record(body.audio_id, stage="asr")
    audio_bytes = record.audio_path.read_bytes()
    text = transcribe_audio(audio_bytes)
    logger.info(
        "asr request_id=%s audio_id=%s text_len=%s",
        request.state.request_id,
        record.audio_id,
        len(text),
    )
    return AsrResponse(
        request_id=request.state.request_id,
        data=AsrData(text=text),
    )
