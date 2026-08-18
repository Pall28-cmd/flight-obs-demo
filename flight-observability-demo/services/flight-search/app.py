import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# SPOG metric registry (new custom business metrics for the Grafana dashboard)
import metrics as m

SERVICE_NAME = "flight-search-service"
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/v1/traces")

# ---------------------------------------------------------------------------
# OpenTelemetry tracing setup
# ---------------------------------------------------------------------------
resource = Resource(attributes={"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(SERVICE_NAME)


# ---------------------------------------------------------------------------
# Structured JSON logging (trace_id / span_id correlated)
# ---------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    def format(self, record):
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        trace_id = format(ctx.trace_id, "032x") if ctx and ctx.trace_id else "0"
        span_id = format(ctx.span_id, "016x") if ctx and ctx.span_id else "0"
        return json.dumps(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "log_level": record.levelname,
                "service_name": SERVICE_NAME,
                "message": record.getMessage(),
                "trace_id": trace_id,
                "span_id": span_id,
            }
        )


logger = logging.getLogger(SERVICE_NAME)
_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title=SERVICE_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
FastAPIInstrumentor.instrument_app(app)

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["service", "method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency (seconds)", ["service", "endpoint"]
)
SEARCH_COUNT = Counter("flight_search_total", "Total flight searches", ["origin", "destination"])

# Pre-create the chaos gauge children so the SPOG "Active Chaos Simulations"
# panel has a series to read from the very first scrape.
m.init_chaos_series()


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_COUNT.labels(SERVICE_NAME, request.method, request.url.path, response.status_code).inc()
    REQUEST_LATENCY.labels(SERVICE_NAME, request.url.path).observe(duration)
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} in {duration:.3f}s")
    return response


# ---------------------------------------------------------------------------
# In-memory flight data (simulated DB / cache)
# ---------------------------------------------------------------------------
FLIGHTS = [
    {"flight_id": "FL100", "origin": "DEL", "destination": "BOM", "airline": "IndiGo", "price": 4500, "seats_available": 32, "departure": "2026-08-20T06:00:00"},
    {"flight_id": "FL101", "origin": "DEL", "destination": "BLR", "airline": "Air India", "price": 6200, "seats_available": 18, "departure": "2026-08-20T09:30:00"},
    {"flight_id": "FL102", "origin": "BOM", "destination": "DEL", "airline": "Vistara", "price": 4800, "seats_available": 25, "departure": "2026-08-20T14:00:00"},
    {"flight_id": "FL103", "origin": "BLR", "destination": "HYD", "airline": "SpiceJet", "price": 3200, "seats_available": 40, "departure": "2026-08-20T11:15:00"},
    {"flight_id": "FL104", "origin": "DEL", "destination": "GOI", "airline": "IndiGo", "price": 5100, "seats_available": 12, "departure": "2026-08-20T16:45:00"},
]

# ---------------------------------------------------------------------------
# Chaos: gradual memory leak
# Mirrors the report's Web Proxy resource-exhaustion pattern (G-01, 78 tickets)
# ---------------------------------------------------------------------------
_leak_store = []
chaos_state = {"memory_leak": False}


def _leak_worker():
    while chaos_state["memory_leak"]:
        _leak_store.append(bytearray(10 * 1024 * 1024))  # allocate 10MB
        m.CHAOS_INJECTIONS.labels(scenario="memory_leak").inc()
        logger.warning(
            f"CHAOS memory-leak active: allocated 10MB block, total_blocks={len(_leak_store)}"
        )
        time.sleep(2)


@app.post("/api/v1/chaos/memory-leak/start")
def start_memory_leak():
    if not chaos_state["memory_leak"]:
        chaos_state["memory_leak"] = True
        m.ACTIVE_CHAOS_SIMULATIONS.labels(scenario="memory_leak").set(1)
        threading.Thread(target=_leak_worker, daemon=True).start()
        logger.warning("CHAOS memory-leak chaos ENABLED")
    return {
        "status": "memory-leak chaos started",
        "mirrors_report_finding": "Web Proxy resource-exhaustion pattern (Gap G-01, 78 tickets)",
    }


@app.post("/api/v1/chaos/memory-leak/stop")
def stop_memory_leak():
    chaos_state["memory_leak"] = False
    _leak_store.clear()
    m.ACTIVE_CHAOS_SIMULATIONS.labels(scenario="memory_leak").set(0)
    logger.info("CHAOS memory-leak chaos DISABLED, memory released")
    return {"status": "memory-leak chaos stopped, memory released"}


@app.get("/api/v1/chaos/status")
def chaos_status():
    return {"memory_leak_active": chaos_state["memory_leak"], "leaked_blocks": len(_leak_store)}


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------
@app.get("/api/v1/flights/search")
def search_flights(origin: str = None, destination: str = None, cabin_class: str = None):
    route = m.normalise_route(origin, destination)
    cabin = m.normalise_cabin_class(cabin_class)
    started = time.perf_counter()
    status_code = "200"

    try:
        with tracer.start_as_current_span("search-flights-db-query") as span:
            span.set_attribute("flight.route", route)
            span.set_attribute("flight.cabin_class", cabin)

            time.sleep(0.05)  # simulate DB/cache round-trip
            results = FLIGHTS
            if origin:
                results = [f for f in results if f["origin"].upper() == origin.upper()]
            if destination:
                results = [f for f in results if f["destination"].upper() == destination.upper()]

            SEARCH_COUNT.labels(origin or "any", destination or "any").inc()  # legacy
            m.FLIGHT_SEARCH_RESULTS.labels(route=route).observe(len(results))
            if not results:
                m.FLIGHT_SEARCH_ZERO_RESULTS.labels(route=route, cabin_class=cabin).inc()

            logger.info(
                f"Flight search executed route={route} cabin_class={cabin} "
                f"origin={origin} destination={destination} results={len(results)}"
            )
            return {"count": len(results), "flights": results}
    except Exception:
        status_code = "500"
        logger.exception(f"Flight search failed route={route}")
        raise
    finally:
        m.FLIGHT_SEARCH_REQUESTS.labels(
            route=route, cabin_class=cabin, status_code=status_code
        ).inc()
        m.FLIGHT_SEARCH_DURATION.labels(route=route, cabin_class=cabin).observe(
            time.perf_counter() - started
        )


@app.get("/api/v1/flights/{flight_id}")
def get_flight(flight_id: str):
    flight = next((f for f in FLIGHTS if f["flight_id"] == flight_id), None)
    if not flight:
        return JSONResponse(status_code=404, content={"error": "flight not found"})
    return flight


@app.get("/health")
def health():
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
