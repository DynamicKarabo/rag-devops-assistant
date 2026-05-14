"""
OpenTelemetry + Prometheus middleware for FastAPI.
"""

import time
import logging
from fastapi import Request
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger(__name__)


def setup_observability(app):
    """
    Attach Prometheus metrics and request timing middleware to the FastAPI app.
    OpenTelemetry is auto-instrumented via environment variables (OTEL_*).
    """
    # Prometheus metrics at /metrics
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics")

    # Request timing middleware
    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
        return response

    logger.info("Observability: Prometheus /metrics + timing middleware enabled")
