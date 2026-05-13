from contextlib import asynccontextmanager
import json
import os
import shutil
import subprocess
import sys

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from search import filter_articles
from users import router as users_router
from compare import router as compare_router

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "..", "data")
FRONTEND_DIR = os.path.join(HERE, "..", "frontend")
PYTHON = shutil.which("python") or sys.executable


@asynccontextmanager
async def lifespan(app: FastAPI):
    #init_index()
    yield


app = FastAPI(title="News Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users_router)
app.include_router(compare_router)


class SearchRequest(BaseModel):
    query: str = ""


@app.get("/data/{filename:path}")
def data_files(filename: str):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.get("/api/progress")
def api_progress():
    apis = ["newsapi", "nyt", "current"]
    done = sum(
        1 for api in apis
        if os.path.isfile(os.path.join(DATA_DIR, f"{api}_articles.json"))
    )
    merged = os.path.isfile(os.path.join(DATA_DIR, "articles.json"))
    return {"done": done, "total": len(apis), "merged": merged}


@app.get("/api/articles")
def api_articles():
    path = os.path.join(DATA_DIR, "articles.json")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="articles.json not found")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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
        proc = subprocess.run(
            [PYTHON, os.path.join(HERE, "..", "webscraper", "refresh.py"), "--query", query],
            check=True,
            timeout=180,
            capture_output=True,
            text=True,
        )
        print(proc.stdout)
        print(proc.stderr)
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        print(e.stderr)
        raise HTTPException(status_code=500, detail=e.stderr or str(e)) from e
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="Scraping timed out") from e

    results = filter_articles(query)
    return {"query": query, "results": results}


if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")