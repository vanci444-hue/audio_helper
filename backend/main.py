import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from starlette.responses import Response

from api.asr import router as asr_router
from api.health import router as health_router
from api.upload import router as upload_router
from config import settings
from schemas import AppError

app = FastAPI(title="语音约碰面地点", version="0.1.0")
app.include_router(health_router)
app.include_router(upload_router)
app.include_router(asr_router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version="3.0.2",
        routes=app.routes,
    )
    body = (schema.get("components") or {}).get("schemas", {}).get("Body_upload_upload_post")
    file_field = (body or {}).get("properties", {}).get("file")
    if isinstance(file_field, dict):
        file_field["type"] = "string"
        file_field["format"] = "binary"
        file_field.pop("contentMediaType", None)
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


@app.middleware("http")
async def attach_request_id(request: Request, call_next) -> Response:
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


def _stage_from_path(path: str) -> str:
    normalized = path.rstrip("/")
    if normalized.endswith("/upload"):
        return "upload"
    if normalized.endswith("/asr"):
        return "asr"
    return "request"


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return exc.to_response(_request_id(request))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    stage = _stage_from_path(request.url.path)
    message = "请求缺少必要字段或字段类型不正确。"
    if stage == "upload":
        message = "请上传字段名为 file 的录音文件。"
    elif stage == "asr":
        message = "请提供 JSON 字段 audio_id。"
    return AppError(422, "VALIDATION_ERROR", message, stage).to_response(_request_id(request))
