import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from constants import (
    ALLOWED_AUDIO_CODECS,
    AUDIO_PROBE_TIMEOUT_SECONDS,
    MAX_AUDIO_SECONDS,
    MIN_AUDIO_SECONDS,
)
from schemas import AppError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProbeResult:
    container: str
    codec: str
    duration_seconds: float
    duration_source: str


def probe_audio_file(path: Path) -> ProbeResult:
    payload = _run_ffprobe(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    format_info = payload.get("format") or {}
    streams = payload.get("streams") or []
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    if not audio_streams:
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "录音格式不受支持，请使用 WebM/Opus 录音，或更换 Chrome、Edge 后重试。",
            "upload",
        )

    audio = audio_streams[0]
    container = str(format_info.get("format_name") or "")
    codec = str(audio.get("codec_name") or "").lower()
    if "webm" not in container.lower() or codec not in ALLOWED_AUDIO_CODECS:
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "录音格式不受支持，请使用 WebM/Opus 录音，或更换 Chrome、Edge 后重试。",
            "upload",
        )

    duration, source = _duration_from_metadata(format_info, audio)
    if duration is None:
        duration = _duration_from_packets(path)
        source = "packet_timestamps"

    if duration is None:
        raise AppError(
            422,
            "AUDIO_DURATION_INVALID",
            "无法确认录音时长，请重新录制后再上传。",
            "upload",
        )
    if duration < MIN_AUDIO_SECONDS or duration > MAX_AUDIO_SECONDS:
        raise AppError(
            422,
            "AUDIO_DURATION_INVALID",
            "录音时长需在 1 到 60 秒之间，请重新录制。",
            "upload",
        )

    logger.info(
        "audio probe ok container=%s codec=%s duration_s=%.3f source=%s",
        container,
        codec,
        duration,
        source,
    )
    return ProbeResult(
        container=container,
        codec=codec,
        duration_seconds=duration,
        duration_source=source,
    )


def _duration_from_metadata(format_info: dict, audio: dict) -> tuple[float | None, str]:
    for source, raw in (
        ("format.duration", format_info.get("duration")),
        ("stream.duration", audio.get("duration")),
        ("format_tags.DURATION", (format_info.get("tags") or {}).get("DURATION")),
        ("stream_tags.DURATION", (audio.get("tags") or {}).get("DURATION")),
    ):
        parsed = _parse_duration(raw)
        if parsed is not None:
            return parsed, source
    return None, ""


def _duration_from_packets(path: Path) -> float | None:
    payload = _run_ffprobe(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "packet=pts_time,duration_time",
            "-print_format",
            "json",
            str(path),
        ]
    )
    packets = payload.get("packets") or []
    last_pts = None
    last_packet_duration = 0.0
    for packet in packets:
        pts = _parse_duration(packet.get("pts_time"))
        if pts is None:
            continue
        last_pts = pts
        packet_duration = _parse_duration(packet.get("duration_time"))
        last_packet_duration = packet_duration if packet_duration is not None else 0.0
    if last_pts is None:
        return None
    return last_pts + last_packet_duration


def _parse_duration(value: object) -> float | None:
    if value is None or value == "" or value == "N/A":
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _run_ffprobe(args: list[str]) -> dict:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=AUDIO_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AppError(
            502,
            "AUDIO_PROBE_UNAVAILABLE",
            "服务器无法校验音频格式，请先安装 FFmpeg（需包含 ffprobe）后再试。",
            "upload",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            504,
            "AUDIO_PROBE_TIMEOUT",
            "音频校验超时，请换一段更短的录音后重试。",
            "upload",
        ) from exc

    if completed.returncode != 0:
        logger.info("ffprobe failed rc=%s stderr=%s", completed.returncode, completed.stderr[-300:])
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "录音格式不受支持，请使用 WebM/Opus 录音，或更换 Chrome、Edge 后重试。",
            "upload",
        )
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "录音格式不受支持，请使用 WebM/Opus 录音，或更换 Chrome、Edge 后重试。",
            "upload",
        ) from exc
