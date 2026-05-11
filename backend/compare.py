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
        raise HTTPException(status_code=400, detail="Two articles required.")

    a1 = req.articles[0]
    a2 = req.articles[1]

    prompt = f"""
Compare these two news articles.

Article 1:
Title: {a1.title}
Source: {a1.src}
Summary: {a1.summary}

Article 2:
Title: {a2.title}
Source: {a2.src}
Summary: {a2.summary}

Return ONLY valid JSON with this exact structure:

{{
  "article1": {{
    "title": "...",
    "source": "...",
    "core_argument": "...",
    "key_points": ["...", "...", "..."]
  }},
  "article2": {{
    "title": "...",
    "source": "...",
    "core_argument": "...",
    "key_points": ["...", "...", "..."]
  }},
  "key_differences": [
    {{
      "label": "Framing",
      "article1": "...",
      "article2": "..."
    }},
    {{
      "label": "Tone",
      "article1": "...",
      "article2": "..."
    }},
    {{
      "label": "Emphasis",
      "article1": "...",
      "article2": "..."
    }}
  ]
}}
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