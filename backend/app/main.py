from fastapi import FastAPI

from app.core.config import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Budget, order, invoice and payment tracking API.",
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


from app.api.router import api_router

from app.api.router import api_router as invoice_api_router
app.include_router(invoice_api_router, prefix="/api")
