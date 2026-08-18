"""
SPOG metric registry — booking-service.

See services/flight-search/metrics.py for the labelling contract. Summary:
  * `service_name` / `environment` are Prometheus target labels, never defined here.
  * All label values below come from bounded, whitelisted sets.
  * Legacy `flight_bookings_total` / `booking_failures_total` are left in app.py
    so alert_rules.yml continues to fire.
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Bounded label vocabularies
# ---------------------------------------------------------------------------
FLIGHT_ROUTES = {
    "FL100": "DEL-BOM",
    "FL101": "DEL-BLR",
    "FL102": "BOM-DEL",
    "FL103": "BLR-HYD",
    "FL104": "DEL-GOI",
}

KNOWN_PAYMENT_METHODS = {"credit_card", "debit_card", "upi", "netbanking", "wallet"}
KNOWN_CABIN_CLASSES = {"economy", "premium_economy", "business"}

# Canonical failure reasons. Anything unmapped becomes "unknown" rather than
# leaking an unbounded exception string into a label.
FAILURE_REASONS = {
    "no_seats",
    "payment_declined",
    "payment_unreachable",
    "payment_timeout",
    "invalid_request",
    "chaos_error_spike",
    "unknown",
}

CHAOS_SCENARIOS = ("error_spike",)


def route_for_flight(flight_id: str | None) -> str:
    return FLIGHT_ROUTES.get((flight_id or "").upper(), "other")


def normalise_payment_method(method: str | None) -> str:
    pm = (method or "credit_card").lower().replace("-", "_").replace(" ", "_")
    return pm if pm in KNOWN_PAYMENT_METHODS else "other"


def normalise_cabin_class(cabin_class: str | None) -> str:
    cc = (cabin_class or "economy").lower()
    return cc if cc in KNOWN_CABIN_CLASSES else "other"


def normalise_reason(reason: str | None) -> str:
    r = (reason or "unknown").lower()
    return r if r in FAILURE_REASONS else "unknown"


# ---------------------------------------------------------------------------
# Booking funnel + outcome metrics
# ---------------------------------------------------------------------------
BOOKING_REQUESTS = Counter(
    "booking_requests_total",
    "All booking attempts received, whatever the outcome. Denominator for "
    "booking success rate.",
    ["route", "payment_method", "cabin_class", "status_code"],
)

BOOKING_SUCCESS = Counter(
    "booking_success_total",
    "Bookings confirmed end to end (seat held and payment captured).",
    ["route", "payment_method", "cabin_class"],
)

BOOKING_FAILURE = Counter(
    "booking_failure_total",
    "Bookings that did not confirm, by canonical failure reason.",
    ["route", "payment_method", "reason"],
)

BOOKING_DURATION = Histogram(
    "booking_duration_seconds",
    "End-to-end booking duration including the downstream payment call.",
    ["route", "payment_method"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0),
)

# ---------------------------------------------------------------------------
# Business value metrics — feed the Leadership "business impact" panels
# ---------------------------------------------------------------------------
BOOKING_VALUE_INR = Counter(
    "booking_value_inr_total",
    "Cumulative confirmed booking value in INR. Rate of this counter is revenue "
    "per second.",
    ["route", "payment_method"],
)

BOOKING_VALUE_AT_RISK_INR = Counter(
    "booking_value_at_risk_inr_total",
    "Cumulative INR value of booking attempts that failed. Rate of this counter "
    "is revenue-at-risk per second.",
    ["route", "payment_method", "reason"],
)

# ---------------------------------------------------------------------------
# Inventory / saturation
# ---------------------------------------------------------------------------
FLIGHT_SEATS_AVAILABLE = Gauge(
    "flight_seats_available",
    "Seats currently available per flight.",
    ["flight_id", "route"],
)

DOWNSTREAM_DEPENDENCY_UP = Gauge(
    "downstream_dependency_up",
    "1 if the last call to a downstream dependency succeeded, else 0.",
    ["dependency"],
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


def init_dependency_series() -> None:
    DOWNSTREAM_DEPENDENCY_UP.labels(dependency="payment-service").set(1)


def publish_inventory(inventory: dict) -> None:
    """Mirror the in-memory seat map into the seats-available gauge."""
    for flight_id, seats in inventory.items():
        FLIGHT_SEATS_AVAILABLE.labels(
            flight_id=flight_id, route=route_for_flight(flight_id)
        ).set(seats)
