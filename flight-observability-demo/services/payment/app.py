# services/payment/app.py - PRODUCTION INSTRUMENTATION

import json
import logging
import os
import time
import random
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

SERVICE_NAME = "payment-service"
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
# OBSERVABILITY: Prometheus Metrics
# ============================================================================

# HTTP Request Metrics
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

# Payment Business Metrics (EXACT dashboard requirements)
payment_processing_duration_seconds = Histogram(
    'payment_processing_duration_seconds',
    'Payment processing duration (seconds)',
    ['payment_method', 'status', 'environment'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

payment_failures_total = Counter(
    'payment_failures_total',
    'Total payment failures',
    ['reason', 'payment_method', 'environment']
)

payment_success_total = Counter(
    'payment_success_total',
    'Total successful payments',
    ['payment_method', 'environment']
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
# ROUTES: Payment API
# ============================================================================

@app.post("/api/v1/payments")
def process_payment(payload: dict):
    amount = payload.get("amount", 0)
    flight_id = payload.get("flight_id", "FL100")
    payment_method = payload.get("payment_method", "credit_card")
    
    # Normalize
    payment_method = "credit_card" if payment_method in ["cc", "credit"] else payment_method
    
    started = time.perf_counter()
    
    # Simulate occasional failures (~5% chance)
    if random.random() < 0.05:
        duration = time.perf_counter() - started
        payment_processing_duration_seconds.labels(
            payment_method=payment_method, status="failed", environment=ENVIRONMENT
        ).observe(duration)
        payment_failures_total.labels(
            reason="declined", payment_method=payment_method, environment=ENVIRONMENT
        ).inc()
        logger.warning(f"❌ Payment declined: {payment_method} ₹{amount}")
        return JSONResponse(
            status_code=402,
            content={"status": "declined", "reason": "Card declined"}
        )
    
    # Simulate realistic processing time (50-500ms)
    processing_time = random.uniform(0.05, 0.5)
    time.sleep(processing_time)
    
    duration = time.perf_counter() - started
    payment_processing_duration_seconds.labels(
        payment_method=payment_method, status="success", environment=ENVIRONMENT
    ).observe(duration)
    payment_success_total.labels(
        payment_method=payment_method, environment=ENVIRONMENT
    ).inc()
    
    logger.info(f"✅ Payment processed: {payment_method} ₹{amount} ({duration:.3f}s)")
    
    return {
        "status": "success",
        "payment_id": f"PAY{int(time.time()*1000)}",
        "amount": amount,
        "method": payment_method
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
    logger.info(f"📊 Metrics endpoint: http://localhost:8003/metrics")
    uvicorn.run(app, host="0.0.0.0", port=8003, log_config=None)
