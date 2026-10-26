"""CORS: which browser origins may call this API.

allow_credentials: the refresh token is an httpOnly cookie, so the frontend calls
/auth/refresh and /auth/logout with credentials: "include". Added last in app.py, so it
is the outermost middleware: a 401 or a 429 still carries the CORS headers the browser
needs to read it."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings


def add_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
