import os
import subprocess
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from search import init_index, router as search_router
from users import router as users_router

from compare import router as compare_router

_REFRESH_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "webscraper", "refresh.py")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_index()  # serve whatever's already on disk while the refresh runs
    subprocess.Popen([sys.executable, _REFRESH_SCRIPT])
    yield


app = FastAPI(title="News Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)
app.include_router(users_router)
app.include_router(compare_router)

_frontend = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend):
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="static")