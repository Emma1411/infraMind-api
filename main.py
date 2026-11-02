from fastapi import FastAPI
from config.settings import get_settings
from controllers import (
    analysis_controller,
    export_controller,
    guides_controller,
    health_controller,
    report_controller,
)
from middlewares.cors import setup_cors

settings = get_settings()

app = FastAPI(title=settings.app_name)

setup_cors(app)

app.include_router(health_controller.router)
app.include_router(analysis_controller.router)
app.include_router(guides_controller.router)
app.include_router(export_controller.router)
app.include_router(report_controller.router)