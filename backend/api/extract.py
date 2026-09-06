import logging

from fastapi import APIRouter, Request

from schemas import ExtractRequest, ExtractResponse
from services.extract import extract_meeting

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/extract", response_model=ExtractResponse)
def extract(request: Request, body: ExtractRequest) -> ExtractResponse:
    data = extract_meeting(body.text, body.city)
    logger.info(
        "extract ok request_id=%s city_a=%s city_b=%s category=%s",
        request.state.request_id,
        data.city_a,
        data.city_b,
        data.category,
    )
    return ExtractResponse(request_id=request.state.request_id, data=data)
