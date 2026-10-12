from fastapi import APIRouter

from app.api.routes.parties import router as parties_router
from app.api.routes.budgets import router as budgets_router
from app.api.routes.orders import router as orders_router

api_router = APIRouter()

api_router.include_router(parties_router)
api_router.include_router(budgets_router)
api_router.include_router(orders_router)
