import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import OpenAI

app = FastAPI()


@app.post("/")
@app.post("/api/compare")
async def compare_articles(request: Request):
    try:
        body = await request.json()
        articles = body.get("articles", [])

        if len(articles) < 2:
            return JSONResponse({"error": "Two articles required."}, status_code=400)

        a1 = articles[0]
        a2 = articles[1]

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""
Compare these two news articles.

Article 1:
Title: {a1.get("title", "")}
Source: {a1.get("src", "")}
Summary: {a1.get("summary", "")}

Article 2:
Title: {a2.get("title", "")}
Source: {a2.get("src", "")}
Summary: {a2.get("summary", "")}

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

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You compare news articles. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        comparison = json.loads(response.choices[0].message.content)
        return {"comparison": comparison}

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)