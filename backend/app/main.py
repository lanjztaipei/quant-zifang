"""FastAPI application factory and default ASGI app for Quant Zifang."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings
from app.core.errors import DomainError
from app.providers.base import Clock, MarketDataFetcher, SystemClock
from app.providers.yfinance_provider import MarketDataProvider, YFinanceFetcher
from app.routers import calculator, holdings, market
from app.storage.holdings_store import JsonHoldingsStore

HTTP_STATUS_CODE_MAP: dict[int, str] = {
    404: "NOT_FOUND",
    409: "BASE_LOT_EXISTS",
    422: "VALIDATION_ERROR",
}


def _format_request_validation_error(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err.get("loc", ()))
        msg = err.get("msg", "驗證失敗")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else "請求參數驗證失敗"


def create_app(
    *,
    settings: Settings | None = None,
    clock: Clock | None = None,
    fetcher: MarketDataFetcher | None = None,
) -> FastAPI:
    cfg = settings or Settings.from_env()
    active_clock = clock or SystemClock()
    active_fetcher = fetcher or YFinanceFetcher()

    application = FastAPI(
        title="Quant Zifang（張良）API",
        description="每日開盤前一次頻率的交易掛單決策支援系統（波動率自適應網格 VAG Grid）",
        version="0.1.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.state.settings = cfg
    application.state.market_provider = MarketDataProvider(
        fetcher=active_fetcher,
        cache_path=cfg.data_dir / "atr_cache.json",
        clock=active_clock,
    )
    application.state.holdings_repo = JsonHoldingsStore(cfg.data_dir / "holdings.json")

    @application.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": "VALIDATION_ERROR",
                "message": _format_request_validation_error(exc),
            },
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = HTTP_STATUS_CODE_MAP.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = str(exc.detail) if exc.detail else "請求發生錯誤"
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": message},
        )

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(market.router, prefix="/api/v1")
    application.include_router(calculator.router, prefix="/api/v1")
    application.include_router(holdings.router, prefix="/api/v1")

    return application


app = create_app()
