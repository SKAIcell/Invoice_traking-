
from fastapi import APIRouter, Depends

from app.api.routes.auth import router as auth_router
from app.api.routes.parties import router as parties_router
from app.api.routes.budgets import router as budgets_router
from app.api.routes.orders import router as orders_router
from app.api.routes.invoices import router as invoices_router
from app.api.routes.payments import router as payments_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.order_invoice_import import router as order_invoice_import_router

from app.core.security import get_current_user

api_router = APIRouter()

# Login must remain accessible without a token.
api_router.include_router(auth_router)

# Require authentication for all business APIs.
protected_dependencies = [Depends(get_current_user)]

api_router.include_router(
    parties_router,
    dependencies=protected_dependencies,
)
api_router.include_router(
    budgets_router,
    dependencies=protected_dependencies,
)
api_router.include_router(
    orders_router,
    dependencies=protected_dependencies,
)
api_router.include_router(
    invoices_router,
    dependencies=protected_dependencies,
)
api_router.include_router(
    payments_router,
    dependencies=protected_dependencies,
)
api_router.include_router(
    dashboard_router,
    dependencies=protected_dependencies,
)
api_router.include_router(
    order_invoice_import_router,
    dependencies=protected_dependencies,
)