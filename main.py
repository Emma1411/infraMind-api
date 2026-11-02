import logging

from fastapi import Depends, FastAPI

from config.settings import get_settings
from controllers import (
    analysis_controller,
    export_controller,
    guides_controller,
    health_controller,
    report_controller,
)
from middlewares.api_key import require_api_key
from middlewares.cors import setup_cors

logger = logging.getLogger(__name__)
settings = get_settings()

if not settings.auth_enabled:
    logger.warning("AUTH_ENABLED=false : les routes ne sont pas protégées (usage local seulement).")
elif not settings.api_keys_list:
    logger.warning("AUTH_ENABLED=true mais API_KEYS est vide : toutes les routes protégées répondront 503.")

app = FastAPI(title=settings.app_name)

setup_cors(app)

protected = [Depends(require_api_key)]


app.include_router(health_controller.router)
app.include_router(analysis_controller.router, dependencies=protected)
app.include_router(guides_controller.router, dependencies=protected)
app.include_router(export_controller.router, dependencies=protected)
app.include_router(report_controller.router, dependencies=protected)