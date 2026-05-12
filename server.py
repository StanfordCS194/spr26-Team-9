#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

PYTHON = shutil.which("python") or sys.executable

HERE = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(HERE, "frontend")
DATA_DIR = os.path.join(HERE, "data")

app = FastAPI(title="News Narrative Tracker")


class SearchRequest(BaseModel):
    query: str = ""


def frontend_file(filename: str):
    path = os.path.join(FRONTEND_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


def data_file(filename: str):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.get("/")
def index():
    return frontend_file("index.html")


@app.get("/data/{filename:path}")
def data_files(filename: str):
    return data_file(filename)


@app.get("/api/articles")
def api_articles():
    return data_file("articles.json")


@app.get("/api/progress")
def api_progress():
    apis = ["newsapi", "nyt", "current"]
    done = sum(
        1 for api in apis
        if os.path.isfile(os.path.join(DATA_DIR, f"{api}_articles.json"))
    )
    merged = os.path.isfile(os.path.join(DATA_DIR, "articles.json"))
    return {"done": done, "total": len(apis), "merged": merged}


@app.post("/search")
def search(payload: SearchRequest):
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="No query provided")

    if os.path.isdir(DATA_DIR):
        for fname in os.listdir(DATA_DIR):
            if fname.endswith("_articles.json"):
                os.remove(os.path.join(DATA_DIR, fname))

    try:
        subprocess.run(
            [
                PYTHON,
                os.path.join(HERE, "webscraper", "refresh.py"),
                "--query",
                query,
            ],
            check=True,
            timeout=180,
        )
        return {"status": "ok"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Scraping timed out") from e


@app.get("/{filename:path}")
def frontend_files(filename: str):
    return frontend_file(filename)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8080, reload=False)