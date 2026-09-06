import base64
import logging

import httpx

from config import settings
from constants import ASR_AUDIO_MIME, ASR_MAX_ENCODED_BYTES, ASR_UPSTREAM_TIMEOUT_SECONDS
from schemas import AppError

logger = logging.getLogger(__name__)


def transcribe_audio(audio_bytes: bytes) -> str:
    if not settings.bailian_api_key:
        raise AppError(
            502,
            "ASR_UPSTREAM_ERROR",
            "语音识别服务未配置或调用失败，请稍后重试。",
            "asr",
        )

    encoded = base64.b64encode(audio_bytes).decode("ascii")
    if len(encoded.encode("ascii")) > ASR_MAX_ENCODED_BYTES:
        raise AppError(
            413,
            "FILE_TOO_LARGE",
            "录音编码后超过识别服务限制，请缩短录音后重试。",
            "asr",
        )

    data_url = f"data:{ASR_AUDIO_MIME};base64,{encoded}"
    payload = {
        "model": settings.bailian_asr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_url},
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {"enable_itn": True},
    }
    headers = {
        "Authorization": f"Bearer {settings.bailian_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=ASR_UPSTREAM_TIMEOUT_SECONDS) as client:
            response = client.post(settings.bailian_asr_url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        logger.info("asr timeout url_host=%s", _host(settings.bailian_asr_url))
        raise AppError(
            504,
            "ASR_TIMEOUT",
            "语音识别超时，请稍后重试。",
            "asr",
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("asr upstream connection error type=%s", type(exc).__name__)
        raise AppError(
            502,
            "ASR_UPSTREAM_ERROR",
            "语音识别服务暂时不可用，请稍后重试。",
            "asr",
        ) from exc

    if response.status_code != 200:
        logger.info("asr upstream http_status=%s", response.status_code)
        raise AppError(
            502,
            "ASR_UPSTREAM_ERROR",
            "语音识别服务暂时不可用，请稍后重试。",
            "asr",
        )

    try:
        body = response.json()
        choices = body.get("choices") or []
        text = ((choices[0] or {}).get("message") or {}).get("content")
    except (ValueError, IndexError, AttributeError, TypeError) as exc:
        logger.info("asr upstream response malformed")
        raise AppError(
            502,
            "ASR_UPSTREAM_ERROR",
            "语音识别服务返回异常，请稍后重试。",
            "asr",
        ) from exc

    if text is None:
        logger.info("asr upstream missing content")
        raise AppError(
            502,
            "ASR_UPSTREAM_ERROR",
            "语音识别服务返回异常，请稍后重试。",
            "asr",
        )

    stripped = str(text).strip()
    if not stripped:
        raise AppError(
            422,
            "ASR_EMPTY_TEXT",
            "没有识别到有效文字，请重新录音后再试。",
            "asr",
        )
    logger.info("asr ok text_len=%s", len(stripped))
    return stripped


def _host(url: str) -> str:
    try:
        return httpx.URL(url).host or "unknown"
    except Exception:
        return "unknown"
