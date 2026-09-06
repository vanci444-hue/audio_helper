import json
import logging

import httpx
from pydantic import ValidationError

from config import BACKEND_DIR, settings
from constants import (
    CATEGORY_ALIASES,
    DEFAULT_MEETUP_CATEGORY,
    EXTRACT_MAX_TOKENS,
    EXTRACT_UPSTREAM_TIMEOUT_SECONDS,
)
from schemas import AppError, ExtractData, ExtractModelOutput

logger = logging.getLogger(__name__)
PROMPT_PATH = BACKEND_DIR / "prompts" / "extract.txt"


def extract_meeting(text: str, page_city: str) -> ExtractData:
    raw = _call_deepseek(text, page_city)
    parsed = _parse_model_output(raw)
    filled = _apply_defaults(parsed, page_city)
    _assert_complete(filled)
    return ExtractData(
        city_a=filled.city_a,
        address_a=filled.address_a,
        city_b=filled.city_b,
        address_b=filled.address_b,
        category=filled.category,
    )


def _call_deepseek(text: str, page_city: str) -> str:
    if not settings.deepseek_api_key:
        raise AppError(
            502,
            "EXTRACT_UPSTREAM_ERROR",
            "地址提取服务未配置或调用失败，请稍后重试。",
            "extract",
        )
    try:
        system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.info("extract prompt missing")
        raise AppError(
            502,
            "EXTRACT_UPSTREAM_ERROR",
            "地址提取服务未配置或调用失败，请稍后重试。",
            "extract",
        ) from exc

    payload = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"页面城市：{page_city}\n用户原话：{text}\n请输出 JSON。",
            },
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_tokens": EXTRACT_MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=EXTRACT_UPSTREAM_TIMEOUT_SECONDS) as client:
            response = client.post(settings.deepseek_api_url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        logger.info("extract timeout host=%s", _host(settings.deepseek_api_url))
        raise AppError(
            504,
            "EXTRACT_TIMEOUT",
            "地址提取超时，请稍后重试。",
            "extract",
        ) from exc
    except httpx.HTTPError as exc:
        logger.info("extract upstream connection error type=%s", type(exc).__name__)
        raise AppError(
            502,
            "EXTRACT_UPSTREAM_ERROR",
            "地址提取服务暂时不可用，请稍后重试。",
            "extract",
        ) from exc

    if response.status_code != 200:
        logger.info("extract upstream http_status=%s", response.status_code)
        raise AppError(
            502,
            "EXTRACT_UPSTREAM_ERROR",
            "地址提取服务暂时不可用，请稍后重试。",
            "extract",
        )

    try:
        body = response.json()
        finish_reason = ((body.get("choices") or [{}])[0] or {}).get("finish_reason")
        content = ((body.get("choices") or [{}])[0] or {}).get("message") or {}
        text_out = content.get("content")
    except (ValueError, IndexError, AttributeError, TypeError) as exc:
        logger.info("extract upstream response malformed")
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "地址信息解析服务返回格式异常，请稍后重试。",
            "extract",
        ) from exc

    if finish_reason == "length" or text_out is None or not str(text_out).strip():
        logger.info("extract model output empty_or_truncated finish_reason=%s", finish_reason)
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "地址信息解析服务返回格式异常，请稍后重试。",
            "extract",
        )
    return str(text_out)


def _parse_model_output(raw: str) -> ExtractModelOutput:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.info("extract model json decode failed")
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "地址信息解析服务返回格式异常，请稍后重试。",
            "extract",
        ) from exc
    if not isinstance(payload, dict):
        logger.info("extract model json is not an object")
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "地址信息解析服务返回格式异常，请稍后重试。",
            "extract",
        )
    try:
        parsed = ExtractModelOutput.model_validate(payload)
    except ValidationError as exc:
        logger.info("extract model schema invalid")
        raise AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "地址信息解析服务返回格式异常，请稍后重试。",
            "extract",
        ) from exc
    logger.info(
        "extract model parsed party_count=%s incomplete=%s",
        parsed.party_count,
        bool(parsed.incomplete_reason),
    )
    return parsed


def _apply_defaults(parsed: ExtractModelOutput, page_city: str) -> ExtractModelOutput:
    page_city = _clean(page_city) or page_city
    return parsed.model_copy(
        update={
            "city_a": _clean(parsed.city_a) or page_city,
            "city_b": _clean(parsed.city_b) or page_city,
            "address_a": _clean(parsed.address_a),
            "address_b": _clean(parsed.address_b),
            "category": _normalize_category(_clean(parsed.category)) or DEFAULT_MEETUP_CATEGORY,
        }
    )


def _assert_complete(filled: ExtractModelOutput) -> None:
    if filled.party_count != 2:
        raise AppError(
            422,
            "PARTY_COUNT_INVALID",
            "目前只支持两个人约碰面。请再说一次你们两个人各自所在的地点。",
            "extract",
        )
    if not all(
        [
            filled.city_a,
            filled.address_a,
            filled.city_b,
            filled.address_b,
            filled.category,
        ]
    ):
        raise AppError(
            422,
            "EXTRACT_INCOMPLETE",
            "地点说得不够具体。请分别说出两个人可以定位的地点，不要只说家或公司。",
            "extract",
        )
    if _normalize_city(filled.city_a) != _normalize_city(filled.city_b):
        raise AppError(
            422,
            "CROSS_CITY_NOT_SUPPORTED",
            "目前只支持同一座城市内约碰面。请确认两人都在同一座城市后再试。",
            "extract",
        )


def _normalize_city(name: str) -> str:
    value = name.strip()
    if value.endswith("市") and len(value) > 1:
        return value[:-1]
    return value


def _normalize_category(name: str | None) -> str | None:
    if not name:
        return None
    return CATEGORY_ALIASES.get(name, name)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _host(url: str) -> str:
    try:
        return httpx.URL(url).host or "unknown"
    except Exception:
        return "unknown"
