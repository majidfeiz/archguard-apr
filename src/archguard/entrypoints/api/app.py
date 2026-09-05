from fastapi import FastAPI

from archguard import __version__
from archguard.infrastructure.config import Settings, load_settings
from archguard.schemas.api import HealthResponse, ReadyResponse, VersionResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    """Readiness means validated configuration; no execution backend exists yet."""
    application = FastAPI(title="ArchGuard-APR", version=__version__)
    application.state.settings = (settings or load_settings()).model_copy(deep=True)

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/ready", response_model=ReadyResponse)
    def ready() -> ReadyResponse:
        return ReadyResponse()

    @application.get("/version", response_model=VersionResponse)
    def version() -> VersionResponse:
        return VersionResponse(version=__version__)

    return application
