import json
import logging
import os
import random
import time
from datetime import datetime, timezone

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# SPOG metric registry (new custom business metrics for the Grafana dashboard)
import metrics as m

SERVICE_NAME = "booking-service"
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/v1/traces")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8003")

# ---------------------------------------------------------------------------
# OpenTelemetry tracing setup (RequestsInstrumentor propagates trace context
# on outbound calls to the Payment service -> single distributed trace)
# ---------------------------------------------------------------------------
resource = Resource(attributes={"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(SERVICE_NAME)
RequestsInstrumentor().instrument()


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

app = FastAPI(title=SERVICE_NAME)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
FastAPIInstrumentor.instrument_app(app)

REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["service", "method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency (seconds)", ["service", "endpoint"]
)
BOOKING_TOTAL = Counter("flight_bookings_total", "Total flight bookings", ["status"])
BOOKING_FAILURES = Counter("booking_failures_total", "Total booking failures", ["reason"])

# Pre-create gauge children so SPOG panels have series from the first scrape.
m.init_chaos_series()
m.init_dependency_series()


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
# In-memory inventory + bookings (simulated DB)
# ---------------------------------------------------------------------------
INVENTORY = {"FL100": 32, "FL101": 18, "FL102": 25, "FL103": 40, "FL104": 12}
BOOKINGS = {}
_booking_counter = 0

# ---------------------------------------------------------------------------
# Chaos: error spike (50% of booking requests fail with HTTP 500)
# Mirrors the report's Active Directory auth-cascade / downstream failure
# pattern, where an upstream fault cascades into a burst of dependent errors.
# ---------------------------------------------------------------------------
chaos_state = {"error_spike": False}


@app.post("/api/v1/chaos/error-spike/start")
def start_error_spike():
    chaos_state["error_spike"] = True
    m.ACTIVE_CHAOS_SIMULATIONS.labels(scenario="error_spike").set(1)
    logger.warning("CHAOS error-spike chaos ENABLED (~50% booking requests will fail)")
    return {
        "status": "error-spike chaos started",
        "mirrors_report_finding": "Active Directory auth-cascade / downstream failure pattern",
    }


@app.post("/api/v1/chaos/error-spike/stop")
def stop_error_spike():
    chaos_state["error_spike"] = False
    m.ACTIVE_CHAOS_SIMULATIONS.labels(scenario="error_spike").set(0)
    logger.info("CHAOS error-spike chaos DISABLED")
    return {"status": "error-spike chaos stopped"}


@app.get("/api/v1/chaos/status")
def chaos_status():
    return {"error_spike_active": chaos_state["error_spike"]}


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------
@app.post("/api/v1/bookings")
def create_booking(payload: dict):
    global _booking_counter
    flight_id = payload.get("flight_id")
    passenger_name = payload.get("passenger_name", "Guest")
    amount = payload.get("amount", 0) or 0

    # --- Normalise every label value up front (bounded cardinality) ----------
    route = m.route_for_flight(flight_id)
    payment_method = m.normalise_payment_method(payload.get("payment_method"))
    cabin_class = m.normalise_cabin_class(payload.get("cabin_class"))
    started = time.perf_counter()

    def _record(status_code: str, reason: str | None = None):
        """Single exit point for all SPOG booking metrics."""
        m.BOOKING_REQUESTS.labels(
            route=route,
            payment_method=payment_method,
            cabin_class=cabin_class,
            status_code=status_code,
        ).inc()
        m.BOOKING_DURATION.labels(route=route, payment_method=payment_method).observe(
            time.perf_counter() - started
        )
        if reason is None:
            m.BOOKING_SUCCESS.labels(
                route=route, payment_method=payment_method, cabin_class=cabin_class
            ).inc()
            m.BOOKING_VALUE_INR.labels(route=route, payment_method=payment_method).inc(amount)
        else:
            canonical = m.normalise_reason(reason)
            m.BOOKING_FAILURE.labels(
                route=route, payment_method=payment_method, reason=canonical
            ).inc()
            m.BOOKING_VALUE_AT_RISK_INR.labels(
                route=route, payment_method=payment_method, reason=canonical
            ).inc(amount)

    span = trace.get_current_span()
    span.set_attribute("flight.route", route)
    span.set_attribute("payment.method", payment_method)
    span.set_attribute("flight.cabin_class", cabin_class)

    # --- Injected chaos: error spike ---------------------------------------
    if chaos_state["error_spike"] and random.random() < 0.5:
        m.CHAOS_INJECTIONS.labels(scenario="error_spike").inc()
        BOOKING_FAILURES.labels("simulated_error_spike").inc()  # legacy
        BOOKING_TOTAL.labels("failed").inc()                    # legacy
        _record("500", "chaos_error_spike")
        logger.error(f"Booking failed for flight {flight_id} due to injected chaos error-spike")
        return JSONResponse(status_code=500, content={"error": "Internal booking error (chaos error-spike active)"})

    # --- Seat inventory ----------------------------------------------------
    with tracer.start_as_current_span("check-seat-inventory"):
        available = INVENTORY.get(flight_id, 0)
        if available <= 0:
            BOOKING_FAILURES.labels("no_seats").inc()  # legacy
            BOOKING_TOTAL.labels("failed").inc()       # legacy
            _record("409", "no_seats")
            logger.warning(f"Booking rejected for flight {flight_id}: no seats available")
            return JSONResponse(status_code=409, content={"error": "No seats available"})

    # --- Downstream payment call ------------------------------------------
    with tracer.start_as_current_span("call-payment-service"):
        try:
            resp = requests.post(
                f"{PAYMENT_SERVICE_URL}/api/v1/payments",
                json={
                    "amount": amount,
                    "flight_id": flight_id,
                    "payment_method": payment_method,
                },
                timeout=10,
            )
            payment_result = resp.json()
            m.DOWNSTREAM_DEPENDENCY_UP.labels(dependency="payment-service").set(1)
        except requests.Timeout as e:
            m.DOWNSTREAM_DEPENDENCY_UP.labels(dependency="payment-service").set(0)
            BOOKING_FAILURES.labels("payment_unreachable").inc()  # legacy
            BOOKING_TOTAL.labels("failed").inc()                  # legacy
            _record("504", "payment_timeout")
            logger.error(f"Payment service timed out: {e}")
            return JSONResponse(status_code=504, content={"error": "Payment service timeout"})
        except Exception as e:
            m.DOWNSTREAM_DEPENDENCY_UP.labels(dependency="payment-service").set(0)
            BOOKING_FAILURES.labels("payment_unreachable").inc()  # legacy
            BOOKING_TOTAL.labels("failed").inc()                  # legacy
            _record("502", "payment_unreachable")
            logger.error(f"Payment service unreachable: {e}")
            return JSONResponse(status_code=502, content={"error": "Payment service unavailable"})

    if payment_result.get("status") != "success":
        BOOKING_FAILURES.labels("payment_declined").inc()  # legacy
        BOOKING_TOTAL.labels("failed").inc()               # legacy
        _record("402", "payment_declined")
        logger.warning(f"Payment declined for flight {flight_id} route={route} method={payment_method}")
        return JSONResponse(status_code=402, content={"error": "Payment declined", "detail": payment_result})

    # --- Confirm ----------------------------------------------------------
    INVENTORY[flight_id] = available - 1
    m.FLIGHT_SEATS_AVAILABLE.labels(flight_id=flight_id, route=route).set(INVENTORY[flight_id])
    _booking_counter += 1
    booking_id = f"BK{1000 + _booking_counter}"
    BOOKINGS[booking_id] = {
        "booking_id": booking_id,
        "flight_id": flight_id,
        "route": route,
        "passenger_name": passenger_name,
        "amount": amount,
        "cabin_class": cabin_class,
        "payment_method": payment_method,
        "status": "confirmed",
        "payment_ref": payment_result.get("payment_id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    BOOKING_TOTAL.labels("confirmed").inc()  # legacy
    _record("201", None)
    logger.info(
        f"Booking confirmed: {booking_id} flight={flight_id} route={route} "
        f"method={payment_method} amount={amount}"
    )
    return BOOKINGS[booking_id]


@app.get("/api/v1/bookings/{booking_id}")
def get_booking(booking_id: str):
    booking = BOOKINGS.get(booking_id)
    if not booking:
        return JSONResponse(status_code=404, content={"error": "booking not found"})
    return booking


@app.get("/api/v1/inventory")
def get_inventory():
    return INVENTORY


@app.get("/health")
def health():
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
