import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from constants import AUDIO_TTL
from main import app
from schemas import AppError

client = TestClient(app)


def _write_audio(tmp_path: Path, audio_id: str, created_at: datetime | None = None) -> None:
    created = created_at or datetime.now(timezone.utc)
    (tmp_path / f"{audio_id}.webm").write_bytes(b"fake-webm-bytes")
    (tmp_path / f"{audio_id}.json").write_text(
        json.dumps(
            {
                "audio_id": audio_id,
                "created_at": created.isoformat(),
                "original_filename": "meetup-recording.webm",
                "codec": "opus",
                "container": "matroska,webm",
                "duration_seconds": 3.2,
                "size_bytes": 15,
            }
        ),
        encoding="utf-8",
    )


def test_asr_success_returns_text(tmp_path, monkeypatch):
    monkeypatch.setattr("services.storage.settings.storage_dir", tmp_path)
    audio_id = "aud_" + "a" * 32
    _write_audio(tmp_path, audio_id)
    with patch("api.asr.transcribe_audio", return_value="我在杭州东站"):
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["data"] == {"text": "我在杭州东站"}


def test_asr_rejects_missing_audio_id():
    response = client.post("/asr", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["stage"] == "asr"


def test_asr_rejects_unknown_audio_id(tmp_path, monkeypatch):
    monkeypatch.setattr("services.storage.settings.storage_dir", tmp_path)
    response = client.post("/asr", json={"audio_id": "aud_" + "b" * 32})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "AUDIO_NOT_FOUND"
    assert body["error"]["stage"] == "asr"


def test_asr_rejects_expired_audio_id(tmp_path, monkeypatch):
    monkeypatch.setattr("services.storage.settings.storage_dir", tmp_path)
    audio_id = "aud_" + "c" * 32
    expired = datetime.now(timezone.utc) - AUDIO_TTL - timedelta(minutes=1)
    _write_audio(tmp_path, audio_id, created_at=expired)
    response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "AUDIO_NOT_FOUND"
    assert body["error"]["stage"] == "asr"


def test_asr_rejects_empty_transcript(tmp_path, monkeypatch):
    monkeypatch.setattr("services.storage.settings.storage_dir", tmp_path)
    audio_id = "aud_" + "d" * 32
    _write_audio(tmp_path, audio_id)
    with patch(
        "api.asr.transcribe_audio",
        side_effect=AppError(
            422,
            "ASR_EMPTY_TEXT",
            "没有识别到有效文字，请重新录音后再试。",
            "asr",
        ),
    ):
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "ASR_EMPTY_TEXT"
    assert body["error"]["stage"] == "asr"


def test_asr_upstream_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("services.storage.settings.storage_dir", tmp_path)
    audio_id = "aud_" + "e" * 32
    _write_audio(tmp_path, audio_id)
    with patch(
        "api.asr.transcribe_audio",
        side_effect=AppError(504, "ASR_TIMEOUT", "语音识别超时，请稍后重试。", "asr"),
    ):
        response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 504
    body = response.json()
    assert body["error"]["code"] == "ASR_TIMEOUT"
    assert body["error"]["stage"] == "asr"


def test_asr_rejects_encoded_payload_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr("services.storage.settings.storage_dir", tmp_path)
    monkeypatch.setattr("services.asr.settings.bailian_api_key", "sk-test")
    monkeypatch.setattr("services.asr.ASR_MAX_ENCODED_BYTES", 8)
    audio_id = "aud_" + "f" * 32
    _write_audio(tmp_path, audio_id)
    response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "FILE_TOO_LARGE"
    assert body["error"]["stage"] == "asr"
