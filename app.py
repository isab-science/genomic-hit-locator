from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


APP_ROOT = Path(__file__).resolve().parent
APP_TITLE = os.getenv("GENOMIC_HIT_LOCATOR_TITLE", "Genomic Hit Locator").strip() or "Genomic Hit Locator"
APP_SUBTITLE = (
    os.getenv(
        "GENOMIC_HIT_LOCATOR_SUBTITLE",
        "Placeholder interface for pooled CRISPR screen follow-up and genomic hit localization.",
    ).strip()
    or "Placeholder interface for pooled CRISPR screen follow-up and genomic hit localization."
)
PUBLIC_BASE_URL = os.getenv("GENOMIC_HIT_LOCATOR_PUBLIC_BASE_URL", "https://genomic-hit-locator.isab.science").strip()
FRAME_ANCESTORS = os.getenv(
    "GENOMIC_HIT_LOCATOR_FRAME_ANCESTORS",
    "'self' https://isab.science https://www.isab.science",
).strip()

app = FastAPI(title=APP_TITLE)
templates = Jinja2Templates(directory=str(APP_ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(APP_ROOT / "static")), name="static")


@app.middleware("http")
async def add_frame_policy(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = f"frame-ancestors {FRAME_ANCESTORS};"
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": APP_TITLE,
            "subtitle": APP_SUBTITLE,
            "public_base_url": PUBLIC_BASE_URL,
        },
    )


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "app": "genomic-hit-locator"})

