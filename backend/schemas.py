from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class HealthData(BaseModel):
    status: str = Field(examples=["ok"])


class HealthResponse(BaseModel):
    request_id: str
    data: HealthData


class UploadData(BaseModel):
    audio_id: str


class UploadResponse(BaseModel):
    request_id: str
    data: UploadData


class AsrRequest(BaseModel):
    audio_id: str = Field(min_length=1, examples=["aud_01hzx"])


class AsrData(BaseModel):
    text: str


class AsrResponse(BaseModel):
    request_id: str
    data: AsrData


class ExtractRequest(BaseModel):
    text: str = Field(
        min_length=1,
        examples=["我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。"],
    )
    city: str = Field(min_length=1, examples=["杭州"])


class ExtractData(BaseModel):
    city_a: str
    address_a: str
    city_b: str
    address_b: str
    category: str


class ExtractResponse(BaseModel):
    request_id: str
    data: ExtractData


class ExtractModelOutput(BaseModel):
    city_a: str | None = None
    address_a: str | None = None
    city_b: str | None = None
    address_b: str | None = None
    category: str | None = None
    party_count: int
    incomplete_reason: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    stage: str


class ErrorResponse(BaseModel):
    request_id: str
    error: ErrorDetail


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, stage: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.stage = stage

    def to_response(self, request_id: str) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content={
                "request_id": request_id,
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "stage": self.stage,
                },
            },
        )
