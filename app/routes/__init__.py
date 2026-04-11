from fastapi import APIRouter

from app.routes.admin import router as admin_router
from app.routes.analytics import router as analytics_router
from app.routes.auth import router as auth_router
from app.routes.billing import router as billing_router
from app.routes.bulk import router as bulk_router
from app.routes.campaigns import router as campaigns_router
from app.routes.contacts import router as contacts_router
from app.routes.health import router as health_router
from app.routes.meta_credentials import router as meta_credentials_router
from app.routes.onboarding import router as onboarding_router
from app.routes.templates import router as templates_router
from app.routes.webhook_meta import router as webhook_meta_router
from app.routes.whatsapp import router as whatsapp_router
from app.routes.workspaces import router as workspace_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(analytics_router)
api_router.include_router(admin_router)
api_router.include_router(auth_router)
api_router.include_router(onboarding_router)
api_router.include_router(workspace_router)
api_router.include_router(billing_router)
api_router.include_router(meta_credentials_router)
api_router.include_router(templates_router)
api_router.include_router(webhook_meta_router)
api_router.include_router(bulk_router)
api_router.include_router(campaigns_router)
api_router.include_router(contacts_router)
api_router.include_router(whatsapp_router)
