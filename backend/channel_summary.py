import os

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

router = APIRouter()


class ChannelArticle(BaseModel):
    title: str
    summary: str | None = ""
    date: str | None = ""


class ChannelSummaryRequest(BaseModel):
    source: str
    articles: list[ChannelArticle]


@router.post("/api/channel-summary")
async def summarize_channel(req: ChannelSummaryRequest):
    if not req.articles:
        raise HTTPException(status_code=400, detail="At least one article is required.")

    article_blocks = "\n\n".join(
        f"""Article {index}:
Date: {article.date}
Title: {article.title}
Summary: {article.summary}"""
        for index, article in enumerate(req.articles[:20], start=1)
    )

    prompt = f"""
Write a concise overview of {req.source}'s coverage using only the supplied articles.

{article_blocks}

Summarize the main angle, recurring themes, and any meaningful development over time.
If only one article is supplied, describe that article's focus without claiming a recurring pattern.
Do not infer political bias, editorial intent, or facts that are not supported by the supplied text.
Write two short paragraphs in plain text. Do not use headings, bullet points, or markdown.
"""

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You summarize a news outlet's coverage using only the provided article text.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.3,
        )
        summary = response.choices[0].message.content
        if not summary:
            raise ValueError("The generated summary was empty.")
        return {"summary": summary.strip()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
