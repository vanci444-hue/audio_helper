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
