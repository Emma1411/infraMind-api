from fastapi import FastAPI

from config.settings import get_settings
from controllers import health_controller
from middlewares.cors import setup_cors

settings = get_settings()

app = FastAPI(title=settings.app_name)

setup_cors(app)

app.include_router(health_controller.router)