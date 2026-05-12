from fastapi import APIRouter

from app.routes.admin import router as admin_router
from app.routes.analytics import router as analytics_router, events_router
from app.routes.dashboard import router as dashboard_router
from app.routes.auth import router as auth_router
from app.routes.billing import router as billing_router
from app.routes.bulk import router as bulk_router
from app.routes.campaigns import router as campaigns_router
from app.routes.contacts import router as contacts_router
from app.routes.contact_activities import router as contact_activities_router
from app.routes.contact_attributes import router as contact_attributes_router
from app.routes.contact_imports import router as contact_imports_router
from app.routes.contact_notes import router as contact_notes_router
from app.routes.ecommerce import router as ecommerce_router
from app.routes.health import router as health_router
from app.routes.meta_credentials import router as meta_credentials_router
from app.routes.onboarding import router as onboarding_router
from app.routes.tags import router as tags_router
from app.routes.templates import router as templates_router
from app.routes.segments import router as segments_router
from app.routes.webhook_meta import router as webhook_meta_router
from app.routes.webhook_order import router as webhook_order_router
from app.routes.whatsapp import router as whatsapp_router
from app.routes.workspaces import router as workspace_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(analytics_router)
api_router.include_router(events_router)
api_router.include_router(dashboard_router)
api_router.include_router(admin_router)
api_router.include_router(auth_router)
api_router.include_router(onboarding_router)
api_router.include_router(workspace_router)
api_router.include_router(billing_router)
api_router.include_router(meta_credentials_router)
api_router.include_router(templates_router)
api_router.include_router(webhook_meta_router)
api_router.include_router(webhook_order_router)
api_router.include_router(bulk_router)
api_router.include_router(campaigns_router)
api_router.include_router(contacts_router)
api_router.include_router(tags_router)
api_router.include_router(segments_router)
api_router.include_router(contact_notes_router)
api_router.include_router(contact_activities_router)
api_router.include_router(contact_attributes_router)
api_router.include_router(contact_imports_router)
api_router.include_router(ecommerce_router)
api_router.include_router(whatsapp_router)
