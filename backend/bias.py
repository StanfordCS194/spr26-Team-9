import json
import os

from fastapi import APIRouter

router = APIRouter()

_BIAS_PATH = os.path.join(os.path.dirname(__file__), "..", "data_public", "bias_all_articles.json")


@router.get("/api/bias")
async def get_bias():
    if not os.path.exists(_BIAS_PATH):
        return {}
    with open(_BIAS_PATH, encoding="utf-8") as f:
        return json.load(f)
