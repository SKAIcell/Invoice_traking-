
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.api.router import api_router


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Budget, order, invoice and payment tracking API.",
)

# CORS configuration for the React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["General"])
def root():
    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "message": "Backend is running successfully",
    }


@app.get("/api/health", tags=["General"])
def health_check():
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")
