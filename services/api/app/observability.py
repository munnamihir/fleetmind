"""FleetMind Phase 9.1 observability wiring.

Prometheus metrics are always exposed when this module is installed.
OpenTelemetry tracing is opt-in through OTEL_ENABLED=true so the local demo
does not require an external collector.
"""

from __future__ import annotations

import os
import time
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from fleetmind_common.db import engine


HTTP_REQUESTS = Counter(
    "fleetmind_http_requests_total",
    "FleetMind HTTP requests",
    ["method", "path", "status"],
)
HTTP_ERRORS = Counter(
    "fleetmind_http_server_errors_total",
    "FleetMind HTTP 5xx responses",
    ["method", "path"],
)
HTTP_LATENCY = Histogram(
    "fleetmind_http_request_duration_seconds",
    "FleetMind HTTP request latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30),
)
HTTP_ACTIVE = Gauge(
    "fleetmind_http_active_requests",
    "Currently active FleetMind HTTP requests",
)

DB_POOL_CHECKED_OUT = Gauge(
    "fleetmind_db_pool_checked_out",
    "SQLAlchemy checked-out connections",
)
DB_POOL_SIZE = Gauge(
    "fleetmind_db_pool_size",
    "SQLAlchemy configured base pool size",
)
DB_POOL_OVERFLOW = Gauge(
    "fleetmind_db_pool_overflow",
    "SQLAlchemy current overflow connections",
)


def _pool_value(method_name: str) -> float:
    method = getattr(engine.pool, method_name, None)
    if method is None:
        return 0.0
    try:
        return float(method())
    except Exception:
        return 0.0


DB_POOL_CHECKED_OUT.set_function(lambda: _pool_value("checkedout"))
DB_POOL_SIZE.set_function(lambda: _pool_value("size"))
DB_POOL_OVERFLOW.set_function(lambda: _pool_value("overflow"))


def _configure_otel(app: FastAPI) -> None:
    if os.getenv("OTEL_ENABLED", "false").lower() not in ("1", "true", "yes", "on"):
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": os.getenv(
                    "OTEL_SERVICE_NAME",
                    "fleetmind-api",
                ),
                "service.version": app.version,
                "deployment.environment": os.getenv(
                    "FLEETMIND_ENV",
                    "development",
                ),
            }
        )
    )

    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,metrics",
    )


def configure_observability(app: FastAPI) -> None:
    """Attach metrics/tracing exactly once."""

    if getattr(app.state, "fleetmind_observability_configured", False):
        return

    app.state.fleetmind_observability_configured = True

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable):
        path = request.url.path
        method = request.method
        started = time.perf_counter()
        HTTP_ACTIVE.inc()

        try:
            response = await call_next(request)
            status = str(response.status_code)
            HTTP_REQUESTS.labels(method=method, path=path, status=status).inc()
            if response.status_code >= 500:
                HTTP_ERRORS.labels(method=method, path=path).inc()
            return response
        except Exception:
            HTTP_REQUESTS.labels(method=method, path=path, status="500").inc()
            HTTP_ERRORS.labels(method=method, path=path).inc()
            raise
        finally:
            HTTP_LATENCY.labels(method=method, path=path).observe(
                time.perf_counter() - started
            )
            HTTP_ACTIVE.dec()

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    _configure_otel(app)
