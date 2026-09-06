from unittest.mock import patch

from fastapi.testclient import TestClient

from constants import MAX_AUDIO_BYTES
from main import app
from schemas import AppError
from services.audio_probe import ProbeResult

client = TestClient(app)


def test_upload_success_returns_audio_id(tmp_path, monkeypatch):
    monkeypatch.setattr("services.storage.settings.storage_dir", tmp_path)
    probe = ProbeResult(
        container="matroska,webm",
        codec="opus",
        duration_seconds=3.2,
        duration_source="packet_timestamps",
    )
    with patch("api.upload.probe_audio_file", return_value=probe):
        response = client.post(
            "/upload",
            files={"file": ("meetup-recording.webm", b"fake-webm-bytes", "audio/webm")},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    audio_id = body["data"]["audio_id"]
    assert audio_id.startswith("aud_")
    assert (tmp_path / f"{audio_id}.webm").is_file()
    assert (tmp_path / f"{audio_id}.json").is_file()


def test_upload_rejects_missing_file_field():
    response = client.post("/upload")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["stage"] == "upload"
    assert "file" in body["error"]["message"]


def test_upload_rejects_unsupported_format():
    with patch(
        "api.upload.probe_audio_file",
        side_effect=AppError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "录音格式不受支持，请使用 WebM/Opus 录音，或更换 Chrome、Edge 后重试。",
            "upload",
        ),
    ):
        response = client.post(
            "/upload",
            files={"file": ("note.txt", b"not-audio", "text/plain")},
        )
    assert response.status_code == 415
    body = response.json()
    assert body["error"] == {
        "code": "UNSUPPORTED_MEDIA_TYPE",
        "message": "录音格式不受支持，请使用 WebM/Opus 录音，或更换 Chrome、Edge 后重试。",
        "stage": "upload",
    }


def test_upload_rejects_file_over_5mb():
    payload = b"x" * (MAX_AUDIO_BYTES + 1)
    response = client.post(
        "/upload",
        files={"file": ("too-big.webm", payload, "audio/webm")},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "FILE_TOO_LARGE"
    assert body["error"]["stage"] == "upload"


def test_upload_rejects_invalid_duration():
    with patch(
        "api.upload.probe_audio_file",
        side_effect=AppError(
            422,
            "AUDIO_DURATION_INVALID",
            "录音时长需在 1 到 60 秒之间，请重新录制。",
            "upload",
        ),
    ):
        response = client.post(
            "/upload",
            files={"file": ("short.webm", b"fake-webm-bytes", "audio/webm")},
        )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "AUDIO_DURATION_INVALID"
    assert body["error"]["stage"] == "upload"
