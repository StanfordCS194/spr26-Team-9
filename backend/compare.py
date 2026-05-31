import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

router = APIRouter()



class Article(BaseModel):
    title: str
    src: str | None = ""
    summary: str | None = ""
    url: str | None = ""


class CompareRequest(BaseModel):
    articles: list[Article]


@router.post("/api/compare")
async def compare_articles(req: CompareRequest):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    if len(req.articles) < 2:
        raise HTTPException(status_code=400, detail="At least two articles required.")

    if len(req.articles) > 3:
        raise HTTPException(status_code=400, detail="Compare up to three articles.")

    articles = req.articles[:3]
    article_blocks = "\n\n".join(
        f"""Article {index}:
Title: {article.title}
Source: {article.src}
Summary: {article.summary}"""
        for index, article in enumerate(articles, start=1)
    )

    expected_json = {
        f"article{index}": {
            "title": "...",
            "source": "...",
            "core_argument": "...",
            "key_points": ["...", "...", "..."],
        }
        for index in range(1, len(articles) + 1)
    }
    expected_json["key_differences"] = [
        {
            "label": label,
            **{f"article{index}": "..." for index in range(1, len(articles) + 1)},
        }
        for label in ("Framing", "Tone", "Emphasis")
    ]

    prompt = f"""
Compare these {len(articles)} news articles.

{article_blocks}

Return ONLY valid JSON with this exact structure:

{json.dumps(expected_json, indent=2)}
"""

    try:
        response = client.chat.completions.create(
    model="gpt-4.1-mini",
    response_format={"type": "json_object"},
    messages=[
        {
            "role": "system",
            "content": "You compare news articles. Return only valid JSON.",
        },
        {
            "role": "user",
            "content": prompt,
        },
    ],
    temperature=0.3,
)

        content = response.choices[0].message.content
        print("OPENAI RAW CONTENT:", content)

        comparison = json.loads(content)

        return {
            "comparison": comparison
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
