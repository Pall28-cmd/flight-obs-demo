# services/booking/app.py - PRODUCTION INSTRUMENTATION

import json
import logging
import os
import time
from datetime import datetime, timezone
import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, Gauge, generate_latest

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = "booking-service"
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/v1/traces")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8003")

# ============================================================================
# OBSERVABILITY: OpenTelemetry Setup
# ============================================================================
resource = Resource(attributes={"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(SERVICE_NAME)
RequestsInstrumentor().instrument()

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

# HTTP Request Metrics (RED method - Rate, Errors, Duration)
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

# Booking Business Metrics (EXACT dashboard requirements)
booking_requests_total = Counter(
    'booking_requests_total',
    'Total booking requests',
    ['route', 'payment_method', 'cabin_class', 'status_code', 'environment']
)

booking_success_total = Counter(
    'booking_success_total',
    'Successful bookings',
    ['route', 'payment_method', 'cabin_class', 'environment']
)

booking_failures_total = Counter(
    'booking_failures_total',
    'Failed bookings',
    ['route', 'payment_method', 'reason', 'environment']
)

booking_value_inr_total = Counter(
    'booking_value_inr_total',
    'Total booking value (INR)',
    ['route', 'payment_method', 'environment']
)

booking_value_at_risk_inr_total = Counter(
    'booking_value_at_risk_inr_total',
    'Booking value at risk (INR)',
    ['route', 'payment_method', 'reason', 'environment']
)

flight_bookings_total = Counter(
    'flight_bookings_total',
    'Total flight bookings',
    ['status', 'environment']
)

booking_duration_seconds = Histogram(
    'booking_duration_seconds',
    'Booking processing duration',
    ['route', 'payment_method', 'environment']
)

# Seat Inventory
flight_seats_available = Gauge(
    'flight_seats_available',
    'Available seats',
    ['flight_id', 'route', 'environment']
)

# Dependency Health
downstream_dependency_up = Gauge(
    'downstream_dependency_up',
    'Downstream dependency status (1=up, 0=down)',
    ['dependency', 'environment']
)

# Search requests (for funnel metrics)
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
# DATA: In-memory inventory
# ============================================================================

INVENTORY = {"FL100": 32, "FL101": 18, "FL102": 25, "FL103": 40, "FL104": 12}
ROUTE_MAP = {
    "FL100": "NYC-LAX", "FL101": "LAX-NYC",
    "FL102": "NYC-MIA", "FL103": "MIA-NYC", "FL104": "LAX-MIA"
}
BOOKINGS = {}
_booking_counter = 0

# Initialize gauges
for flight_id, seats in INVENTORY.items():
    route = ROUTE_MAP.get(flight_id, "unknown")
    flight_seats_available.labels(flight_id=flight_id, route=route, environment=ENVIRONMENT).set(seats)

downstream_dependency_up.labels(dependency="payment-service", environment=ENVIRONMENT).set(1)

# ============================================================================
# ROUTES: Booking API
# ============================================================================

@app.post("/api/v1/bookings")
def create_booking(payload: dict):
    global _booking_counter
    
    flight_id = payload.get("flight_id", "FL100")
    passenger_name = payload.get("passenger_name", "Guest")
    amount = payload.get("amount", 0) or 0
    payment_method = payload.get("payment_method", "credit_card")
    cabin_class = payload.get("cabin_class", "economy")
    
    # Normalize labels
    route = ROUTE_MAP.get(flight_id, "unknown")
    payment_method = "credit_card" if payment_method in ["cc", "credit"] else payment_method
    cabin_class = cabin_class.lower()
    
    started = time.perf_counter()
    
    def _record_metric(status_code, reason=None):
        duration = time.perf_counter() - started
        booking_requests_total.labels(
            route=route, payment_method=payment_method, cabin_class=cabin_class,
            status_code=status_code, environment=ENVIRONMENT
        ).inc()
        booking_duration_seconds.labels(
            route=route, payment_method=payment_method, environment=ENVIRONMENT
        ).observe(duration)
        
        if reason is None:
            booking_success_total.labels(
                route=route, payment_method=payment_method, cabin_class=cabin_class,
                environment=ENVIRONMENT
            ).inc()
            booking_value_inr_total.labels(
                route=route, payment_method=payment_method, environment=ENVIRONMENT
            ).inc(amount)
        else:
            booking_failures_total.labels(
                route=route, payment_method=payment_method, reason=reason,
                environment=ENVIRONMENT
            ).inc()
            booking_value_at_risk_inr_total.labels(
                route=route, payment_method=payment_method, reason=reason,
                environment=ENVIRONMENT
            ).inc(amount)
    
    # Set span attributes for tracing
    span = trace.get_current_span()
    span.set_attribute("flight.route", route)
    span.set_attribute("payment.method", payment_method)
    
    # Check inventory
    with tracer.start_as_current_span("check-inventory"):
        available = INVENTORY.get(flight_id, 0)
        if available <= 0:
            booking_failures_total.labels(
                route=route, payment_method=payment_method, reason="no_seats",
                environment=ENVIRONMENT
            ).inc()
            flight_bookings_total.labels(status="failed", environment=ENVIRONMENT).inc()
            _record_metric("409", "no_seats")
            logger.warning(f"Booking rejected: no seats for {flight_id}")
            return JSONResponse(status_code=409, content={"error": "No seats available"})
    
    # Call payment service
    with tracer.start_as_current_span("call-payment-service"):
        try:
            resp = requests.post(
                f"{PAYMENT_SERVICE_URL}/api/v1/payments",
                json={"amount": amount, "flight_id": flight_id, "payment_method": payment_method},
                timeout=10,
            )
            payment_result = resp.json()
            downstream_dependency_up.labels(dependency="payment-service", environment=ENVIRONMENT).set(1)
        except Exception as e:
            downstream_dependency_up.labels(dependency="payment-service", environment=ENVIRONMENT).set(0)
            booking_failures_total.labels(
                route=route, payment_method=payment_method, reason="payment_unreachable",
                environment=ENVIRONMENT
            ).inc()
            flight_bookings_total.labels(status="failed", environment=ENVIRONMENT).inc()
            _record_metric("502", "payment_unreachable")
            logger.error(f"Payment service error: {e}")
            return JSONResponse(status_code=502, content={"error": "Payment service unavailable"})
    
    if payment_result.get("status") != "success":
        booking_failures_total.labels(
            route=route, payment_method=payment_method, reason="payment_declined",
            environment=ENVIRONMENT
        ).inc()
        flight_bookings_total.labels(status="failed", environment=ENVIRONMENT).inc()
        _record_metric("402", "payment_declined")
        logger.warning(f"Payment declined for {flight_id}")
        return JSONResponse(status_code=402, content={"error": "Payment declined"})
    
    # Confirm booking
    INVENTORY[flight_id] = available - 1
    flight_seats_available.labels(flight_id=flight_id, route=route, environment=ENVIRONMENT).set(INVENTORY[flight_id])
    
    _booking_counter += 1
    booking_id = f"BK{1000 + _booking_counter}"
    
    flight_bookings_total.labels(status="confirmed", environment=ENVIRONMENT).inc()
    _record_metric("201", None)
    
    logger.info(f"✅ Booking confirmed: {booking_id} ({route}, {payment_method}, ₹{amount})")
    
    return {
        "booking_id": booking_id,
        "flight_id": flight_id,
        "route": route,
        "status": "confirmed",
        "amount": amount,
        "payment_ref": payment_result.get("payment_id")
    }

@app.get("/api/v1/bookings/{booking_id}")
def get_booking(booking_id: str):
    if booking_id not in BOOKINGS:
        return JSONResponse(status_code=404, content={"error": "booking not found"})
    return BOOKINGS[booking_id]

@app.get("/api/v1/inventory")
def get_inventory():
    return INVENTORY

@app.get("/api/v1/search")
def search_flights(origin: str = None, destination: str = None):
    """Record search requests for funnel metrics"""
    route = f"{origin or 'NYC'}-{destination or 'LAX'}"
    flight_search_requests_total.labels(route=route, environment=ENVIRONMENT).inc()
    
    return {
        "flights": [
            {"id": "FL100", "from": origin or "NYC", "to": destination or "LAX", "price": 299.99},
            {"id": "FL101", "from": origin or "NYC", "to": destination or "LAX", "price": 349.99},
        ]
    }

@app.get("/health")
def health():
    return {"status": "healthy", "service": SERVICE_NAME}

@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 Starting {SERVICE_NAME}")
    logger.info(f"📊 Metrics endpoint: http://localhost:8002/metrics")
    uvicorn.run(app, host="0.0.0.0", port=8002, log_config=None)
