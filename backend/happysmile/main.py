"""FastAPI app: API under /v1, the public enquiry form at /, the staff console at /console."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import disclosures
from .api import router
from .config import get_settings
from .db import close_pool, init_pool, tx

STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()  # fail fast on bad production config
    init_pool()
    with tx() as conn:
        disclosures.register_all(conn)
    stop, worker = threading.Event(), None
    if s.run_worker:  # one-service hosting (e.g. Railway): the call worker runs alongside the web server
        from . import orchestrator
        worker = threading.Thread(target=orchestrator.run_forever, kwargs={"stop": stop}, name="hs-worker", daemon=True)
        worker.start()
    yield
    stop.set()
    if worker:
        worker.join(timeout=10)
    close_pool()


app = FastAPI(title="HappySmile lead callback platform", version="0.2.0", lifespan=lifespan,
              docs_url="/v1/docs", openapi_url="/v1/openapi.json")
app.include_router(router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy",
                                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
                                if not request.url.path.startswith("/v1/docs") else "frame-ancestors 'none'")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if request.url.path.startswith("/v1/") and request.url.path != "/v1/enquiry-config":
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover - last-resort handler
    return JSONResponse({"error": "server_error", "message": "Something went wrong. Please try again."}, status_code=500)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    from fastapi import Response
    return Response(status_code=204)


@app.get("/healthz", include_in_schema=False)
def healthz():
    with tx() as conn:
        conn.execute("SELECT 1")
    return {"ok": True, "env": get_settings().env}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def enquiry_page():
    return FileResponse(STATIC / "enquiry" / "index.html")


@app.get("/console", include_in_schema=False)
def console_page():
    return FileResponse(STATIC / "console" / "index.html")


@app.get("/voice", include_in_schema=False)
def voice_page():
    """Browser voice demo: talk to the assistant with the microphone (practice call, nothing booked)."""
    return FileResponse(STATIC / "voice" / "index.html")
