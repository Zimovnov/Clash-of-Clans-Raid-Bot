from aiogram import Dispatcher

from app.integrations.telegram.handlers.admin import router as admin_router
from app.integrations.telegram.handlers.clans import router as clans_router
from app.integrations.telegram.handlers.common import router as common_router
from app.integrations.telegram.handlers.reports import router as reports_router


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(common_router)
    dp.include_router(clans_router)
    dp.include_router(reports_router)
    dp.include_router(admin_router)
    return dp
