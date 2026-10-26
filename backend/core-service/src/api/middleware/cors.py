"""CORS: which browser origins may call this API.

Added last in app.py, so it is the outermost middleware: a 401 or a 429 still carries
the CORS headers the browser needs to read it. Content-Disposition is exposed so the
frontend can read the payroll file's name."""

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
        expose_headers=["Content-Disposition"],  # the payroll CSV's file name
    )
