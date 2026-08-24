# services/flight-search/app.py - PRODUCTION INSTRUMENTATION

import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = "flight-search-service"
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/v1/traces")

# ============================================================================
# OBSERVABILITY: OpenTelemetry Setup
# ============================================================================
resource = Resource(attributes={"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(SERVICE_NAME)

# ============================================================================
# OBSERVABILITY: Structured JSON Logging
# ============================================================================
class JsonFormatter(logging.Formatter):
    def format(self, record):
        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        trace_id = format(ctx.trace_id, "032x") if ctx and ctx.trace_id else "0"
        span_id = format(ctx.span_id, "016x") if ctx and ctx.span_id else "0"
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "log_level": record.levelname,
            "service_name": SERVICE_NAME,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
        })

logger = logging.getLogger(SERVICE_NAME)
_handler = logging.StreamHandler()
_handler.setFormatter(JsonFormatter())
logger.addHandler(_handler)
logger.setLevel(logging.INFO)
logger.propagate = False

# ============================================================================
# OBSERVABILITY: Prometheus Metrics - EXACT NAMES MATCHED TO DASHBOARDS
# ============================================================================

# HTTP Request Metrics (RED method)
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['service', 'method', 'endpoint', 'status', 'environment']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency (seconds)',
    ['service', 'endpoint', 'environment'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

# Flight Search Business Metrics (EXACT dashboard requirements)
flight_search_requests_total = Counter(
    'flight_search_requests_total',
    'Total flight search requests',
    ['route', 'environment']
)

# ============================================================================
# FASTAPI SETUP
# ============================================================================

app = FastAPI(title=SERVICE_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
FastAPIInstrumentor.instrument_app(app)

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")

# ============================================================================
# MIDDLEWARE: Request/Response Tracking
# ============================================================================

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    
    # Record HTTP metrics
    http_requests_total.labels(
        service=SERVICE_NAME,
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
        environment=ENVIRONMENT
    ).inc()
    
    http_request_duration_seconds.labels(
        service=SERVICE_NAME,
        endpoint=request.url.path,
        environment=ENVIRONMENT
    ).observe(duration)
    
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration:.3f}s)")
    return response

# ============================================================================
# DATA: Flight inventory
# ============================================================================

FLIGHTS_DB = {
    "NYC-LAX": [
        {"id": "FL100", "departure": "10:00", "arrival": "14:00", "price": 299.99, "seats": 120},
        {"id": "FL101", "departure": "14:30", "arrival": "18:30", "price": 349.99, "seats": 95},
    ],
    "LAX-NYC": [
        {"id": "FL101", "departure": "08:00", "arrival": "16:00", "price": 329.99, "seats": 110},
        {"id": "FL102", "departure": "19:00", "arrival": "03:30+1", "price": 289.99, "seats": 85},
    ],
    "NYC-MIA": [
        {"id": "FL102", "departure": "06:00", "arrival": "09:00", "price": 199.99, "seats": 150},
        {"id": "FL103", "departure": "12:00", "arrival": "15:00", "price": 249.99, "seats": 95},
    ],
    "MIA-NYC": [
        {"id": "FL103", "departure": "09:00", "arrival": "12:00", "price": 219.99, "seats": 130},
        {"id": "FL104", "departure": "15:30", "arrival": "18:30", "price": 269.99, "seats": 75},
    ],
    "LAX-MIA": [
        {"id": "FL104", "departure": "11:00", "arrival": "17:00", "price": 259.99, "seats": 100},
        {"id": "FL100", "departure": "20:00", "arrival": "02:00+1", "price": 319.99, "seats": 110},
    ],
}

# ============================================================================
# ROUTES: Flight Search API
# ============================================================================

@app.get("/api/v1/search")
def search_flights(origin: str = "NYC", destination: str = "LAX"):
    """Search for available flights - feeds flight_search_requests_total metric"""
    route = f"{origin}-{destination}"
    
    with tracer.start_as_current_span("search-flights"):
        # Record search request
        flight_search_requests_total.labels(
            route=route,
            environment=ENVIRONMENT
        ).inc()
        
        # Get flights for this route
        flights = FLIGHTS_DB.get(route, [])
        
        logger.info(f"✅ Search: {route} → {len(flights)} flights found")
        
        return {
            "route": route,
            "origin": origin,
            "destination": destination,
            "flights": flights,
            "count": len(flights)
        }

@app.get("/api/v1/flights/{flight_id}")
def get_flight_details(flight_id: str):
    """Get details for a specific flight"""
    
    # Search across all routes
    for route, flights in FLIGHTS_DB.items():
        for flight in flights:
            if flight["id"] == flight_id:
                logger.info(f"✅ Flight details: {flight_id} ({route})")
                return {**flight, "route": route}
    
    logger.warning(f"❌ Flight not found: {flight_id}")
    return {"error": f"Flight {flight_id} not found"}, 404

@app.get("/health")
def health():
    return {"status": "healthy", "service": SERVICE_NAME}

@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 Starting {SERVICE_NAME}")
    logger.info(f"📊 Metrics endpoint: http://localhost:8001/metrics")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=None)
