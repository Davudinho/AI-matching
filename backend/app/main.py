"""
backend/app/main.py — FastAPI Application Entry Point

This is the root of the FastAPI application.

FastAPI auto-generates interactive API documentation at:
  http://localhost:8000/docs    ← Swagger UI (try requests in browser)
  http://localhost:8000/redoc  ← ReDoc (cleaner docs)

When running:
  uvicorn backend.app.main:app --reload --port 8000
"""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.config import settings
from backend.app.api.routes import jds, candidates, matching, health, auth

# Create the FastAPI application
app = FastAPI(
    title="Diversifying.io AI Recruitment API",
    description=(
        "AI-powered candidate matching for recruiters. "
        "Upload JDs and CVs, get semantic match scores and explainable recommendations."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---- CORS Middleware ----
# In development: allow all origins.
# In production: allow the configured FRONTEND_URL + any *.vercel.app subdomain.
# allow_origin_regex covers all Vercel preview and production deployments automatically.
_allowed_origins = (
    ["*"]
    if settings.ENVIRONMENT == "development"
    else [o.strip() for o in settings.FRONTEND_URL.split(",") if o.strip()]
)
_origin_regex = None if settings.ENVIRONMENT == "development" else r"https://.*\.vercel\.app"
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Register Routers ----
# Each router handles a group of related endpoints.
# The prefix becomes part of the URL: /api/v1/jds, /api/v1/candidates, etc.
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(jds.router, prefix="/api/v1/jds", tags=["Job Descriptions"])
app.include_router(candidates.router, prefix="/api/v1/candidates", tags=["Candidates"])
app.include_router(matching.router, prefix="/api/v1/matching", tags=["Matching"])


@app.get("/", response_class=JSONResponse, tags=["root"])
async def root():
    """Root endpoint — useful for checking the API is running."""
    return {
        "message": "Diversifying.io AI Recruitment API",
        "version": "0.1.0",
        "docs": "/docs",
        "environment": settings.ENVIRONMENT,
    }


# ---- Global error handler ----
# Returns the actual error message instead of opaque "Internal Server Error"
logger = logging.getLogger("dyversifying")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = traceback.format_exc()
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}\n{tb}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"{type(exc).__name__}: {str(exc)}"},
    )
