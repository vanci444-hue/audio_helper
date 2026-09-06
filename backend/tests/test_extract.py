from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from schemas import AppError, ExtractData, ExtractModelOutput
from services.extract import _assert_complete, _parse_model_output

client = TestClient(app)

COMPLETE = ExtractData(
    city_a="杭州",
    address_a="杭州东站",
    city_b="杭州",
    address_b="西湖龙翔桥地铁站",
    category="咖啡店",
)


def test_extract_success_returns_five_fields_only():
    with patch("api.extract.extract_meeting", return_value=COMPLETE):
        response = client.post(
            "/extract",
            json={
                "text": "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。",
                "city": "杭州",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"]
    assert body["data"] == {
        "city_a": "杭州",
        "address_a": "杭州东站",
        "city_b": "杭州",
        "address_b": "西湖龙翔桥地铁站",
        "category": "咖啡店",
    }
    assert "party_count" not in body["data"]
    assert "incomplete_reason" not in body["data"]


def test_extract_rejects_missing_fields():
    response = client.post("/extract", json={"text": "我在杭州东站"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["stage"] == "extract"


def test_extract_party_count_invalid():
    with patch(
        "api.extract.extract_meeting",
        side_effect=AppError(
            422,
            "PARTY_COUNT_INVALID",
            "目前只支持两个人约碰面。请再说一次你们两个人各自所在的地点。",
            "extract",
        ),
    ):
        response = client.post(
            "/extract",
            json={"text": "我们三个人，我在东站，小李在龙翔桥，小王在湖滨。", "city": "杭州"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PARTY_COUNT_INVALID"


def test_extract_incomplete_address():
    with patch(
        "api.extract.extract_meeting",
        side_effect=AppError(
            422,
            "EXTRACT_INCOMPLETE",
            "地点说得不够具体。请分别说出两个人可以定位的地点，不要只说家或公司。",
            "extract",
        ),
    ):
        response = client.post(
            "/extract",
            json={"text": "我在家，朋友在西湖龙翔桥地铁站，找个咖啡店。", "city": "杭州"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EXTRACT_INCOMPLETE"


def test_extract_cross_city():
    with patch(
        "api.extract.extract_meeting",
        side_effect=AppError(
            422,
            "CROSS_CITY_NOT_SUPPORTED",
            "目前只支持同一座城市内约碰面。请确认两人都在同一座城市后再试。",
            "extract",
        ),
    ):
        response = client.post(
            "/extract",
            json={"text": "我在杭州东站，朋友在上海虹桥，找个咖啡店。", "city": "杭州"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CROSS_CITY_NOT_SUPPORTED"


def test_extract_model_invalid_json_is_502_not_user_incomplete():
    with patch(
        "api.extract.extract_meeting",
        side_effect=AppError(
            502,
            "MODEL_OUTPUT_INVALID",
            "地址信息解析服务返回格式异常，请稍后重试。",
            "extract",
        ),
    ):
        response = client.post(
            "/extract",
            json={"text": "我在杭州东站，朋友在龙翔桥。", "city": "杭州"},
        )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MODEL_OUTPUT_INVALID"


def test_parse_model_output_rejects_missing_party_count():
    try:
        _parse_model_output('{"city_a":"杭州","address_a":"东站","city_b":"杭州","address_b":"龙翔桥","category":"咖啡店"}')
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "MODEL_OUTPUT_INVALID"
    else:
        raise AssertionError("expected MODEL_OUTPUT_INVALID")


def test_assert_complete_treats_hangzhou_alias_as_same_city():
    _assert_complete(
        ExtractModelOutput(
            city_a="杭州市",
            address_a="杭州东站",
            city_b="杭州",
            address_b="龙翔桥地铁站",
            category="咖啡店",
            party_count=2,
            incomplete_reason=None,
        )
    )


def test_assert_complete_rejects_yuhang_as_cross_city():
    try:
        _assert_complete(
            ExtractModelOutput(
                city_a="杭州",
                address_a="杭州东站",
                city_b="余杭",
                address_b="余杭高铁站",
                category="咖啡店",
                party_count=2,
                incomplete_reason=None,
            )
        )
    except AppError as exc:
        assert exc.code == "CROSS_CITY_NOT_SUPPORTED"
    else:
        raise AssertionError("expected CROSS_CITY_NOT_SUPPORTED")
