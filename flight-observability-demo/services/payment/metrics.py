"""
SPOG metric registry — payment-service.

See services/flight-search/metrics.py for the labelling contract. Summary:
  * `service_name` / `environment` are Prometheus target labels, never defined here.
  * All label values below come from bounded, whitelisted sets.
  * Legacy `payment_success_total` / `payment_failures_total` /
    `payment_processing_duration_seconds` stay in app.py so alert_rules.yml
    continues to fire.
"""

import os

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Bounded label vocabularies
# ---------------------------------------------------------------------------
GATEWAY_NAME = os.getenv("PAYMENT_GATEWAY_NAME", "razorpay-sim")

KNOWN_PAYMENT_METHODS = {"credit_card", "debit_card", "upi", "netbanking", "wallet"}

# Canonical decline reasons. "none" is used on the success path so the
# `payment_transactions_total` series set stays uniform and joinable.
DECLINE_REASONS = {
    "none",
    "gateway_declined",
    "insufficient_funds",
    "risk_rejected",
    "gateway_timeout",
    "invalid_instrument",
}

CHAOS_SCENARIOS = ("latency",)


def normalise_payment_method(method: str | None) -> str:
    pm = (method or "credit_card").lower().replace("-", "_").replace(" ", "_")
    return pm if pm in KNOWN_PAYMENT_METHODS else "other"


def normalise_decline_reason(reason: str | None) -> str:
    r = (reason or "none").lower()
    return r if r in DECLINE_REASONS else "gateway_declined"


# ---------------------------------------------------------------------------
# Gateway latency — the metric the wireframe's payment latency panels bind to
# ---------------------------------------------------------------------------
PAYMENT_GATEWAY_LATENCY = Histogram(
    "payment_gateway_latency_seconds",
    "Latency of the outbound payment gateway call in seconds. Buckets are "
    "chosen so the 0.5s and 2.0s SLO thresholds are exact bucket boundaries.",
    ["payment_method", "gateway", "status"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0),
)

# ---------------------------------------------------------------------------
# Transaction outcomes
# ---------------------------------------------------------------------------
PAYMENT_TRANSACTIONS = Counter(
    "payment_transactions_total",
    "Payment transactions attempted, by method, gateway, outcome and decline "
    "reason. `decline_reason=none` on the success path.",
    ["payment_method", "gateway", "status", "decline_reason"],
)

PAYMENT_AMOUNT_INR = Counter(
    "payment_amount_inr_total",
    "Cumulative INR value of captured payments.",
    ["payment_method", "gateway"],
)

PAYMENT_AMOUNT_DECLINED_INR = Counter(
    "payment_amount_declined_inr_total",
    "Cumulative INR value of declined payment attempts.",
    ["payment_method", "gateway", "decline_reason"],
)

PAYMENT_IN_FLIGHT = Gauge(
    "payment_requests_in_flight",
    "Payment requests currently being processed — saturation signal.",
    ["gateway"],
)

PAYMENT_GATEWAY_UP = Gauge(
    "payment_gateway_up",
    "1 if the payment gateway is reachable and answering, else 0.",
    ["gateway"],
)

# ---------------------------------------------------------------------------
# Chaos / experiment state
# ---------------------------------------------------------------------------
ACTIVE_CHAOS_SIMULATIONS = Gauge(
    "active_chaos_simulations",
    "1 while a chaos scenario is active in this service, else 0.",
    ["scenario"],
)

CHAOS_INJECTIONS = Counter(
    "chaos_injections_total",
    "Count of individual chaos fault injections applied.",
    ["scenario"],
)


def init_chaos_series() -> None:
    for scenario in CHAOS_SCENARIOS:
        ACTIVE_CHAOS_SIMULATIONS.labels(scenario=scenario).set(0)


def init_gateway_series() -> None:
    PAYMENT_GATEWAY_UP.labels(gateway=GATEWAY_NAME).set(1)
    PAYMENT_IN_FLIGHT.labels(gateway=GATEWAY_NAME).set(0)
