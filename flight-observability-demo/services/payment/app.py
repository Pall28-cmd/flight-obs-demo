import json
import logging
import os
import random
import time
import uuid
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

SERVICE_NAME = "payment-service"
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318/v1/traces")

resource = Resource(attributes={"service.name": SERVICE_NAME})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(SERVICE_NAME)


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
PAYMENT_SUCCESS = Counter("payment_success_total", "Total successful payments")
PAYMENT_FAILURES = Counter("payment_failures_total", "Total failed payments", ["reason"])
PAYMENT_DURATION = Histogram("payment_processing_duration_seconds", "Payment processing duration (seconds)")


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
# Chaos: 3-5s artificial latency injection
# Mirrors the report's Web Proxy / Application Gateway resource-exhaustion
# -> latency degradation pattern (P-01: >85% CPU predicts connectivity /
# latency failures 15-30 minutes downstream).
# ---------------------------------------------------------------------------
chaos_state = {"latency": False}


@app.post("/api/v1/chaos/latency/start")
def start_latency_chaos():
    chaos_state["latency"] = True
    logger.warning("CHAOS latency chaos ENABLED (3-5s delay injected per payment)")
    return {
        "status": "latency chaos started (3-5s delay injected)",
        "mirrors_report_finding": "Resource-exhaustion -> latency degradation pattern (P-01)",
    }


@app.post("/api/v1/chaos/latency/stop")
def stop_latency_chaos():
    chaos_state["latency"] = False
    logger.info("CHAOS latency chaos DISABLED")
    return {"status": "latency chaos stopped"}


@app.get("/api/v1/chaos/status")
def chaos_status():
    return {"latency_chaos_active": chaos_state["latency"]}


@app.post("/api/v1/payments")
def process_payment(payload: dict):
    amount = payload.get("amount", 0)
    flight_id = payload.get("flight_id")
    start = time.time()

    with tracer.start_as_current_span("process-payment-gateway-call"):
        if chaos_state["latency"]:
            delay = random.uniform(3, 5)
            logger.warning(f"CHAOS latency injected: sleeping {delay:.2f}s")
            time.sleep(delay)
        else:
            time.sleep(random.uniform(0.05, 0.2))

        success = random.random() < 0.92  # ~92% baseline success rate
        duration = time.time() - start
        PAYMENT_DURATION.observe(duration)

        if not success:
            PAYMENT_FAILURES.labels("gateway_declined").inc()
            logger.error(f"Payment declined for flight {flight_id}, amount {amount}")
            return {"status": "failed", "reason": "gateway_declined"}

        payment_id = f"PAY-{uuid.uuid4().hex[:10]}"
        PAYMENT_SUCCESS.inc()
        logger.info(f"Payment {payment_id} succeeded for flight {flight_id}, amount {amount}")
        return {"status": "success", "payment_id": payment_id, "amount": amount}


@app.get("/health")
def health():
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
