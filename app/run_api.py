import uvicorn

from app.core.config import get_settings
from app.core.logging import configure_logging


if __name__ == "__main__":
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "app.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
        server_header=False,
        date_header=False,
    )
