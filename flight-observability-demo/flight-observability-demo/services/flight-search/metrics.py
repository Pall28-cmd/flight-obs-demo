"""
SPOG metric registry — flight-search-service.

Design rules (keep these when extending):

1. TOPOLOGY labels are injected by Prometheus at scrape time, NOT here.
   `service_name` and `environment` come from `prometheus.yml` target labels.
   Never define them on a metric or Prometheus will rename yours to
   `exported_service_name` and the $service dashboard variable will break.

2. MEASUREMENT labels are defined here: route, cabin_class, status_code, ...
   Every label value must come from a bounded set. Free-form user input is
   normalised through a whitelist first (see `normalise_route`).

3. Legacy metrics (`flight_search_total`, `http_requests_total`, ...) stay in
   app.py untouched so the existing dashboard and alert_rules.yml keep working.
"""

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Bounded label vocabularies — cardinality guard rails
# ---------------------------------------------------------------------------
KNOWN_ROUTES = {
    "DEL-BOM",
    "DEL-BLR",
    "DEL-GOI",
    "BOM-DEL",
    "BLR-HYD",
}
KNOWN_CABIN_CLASSES = {"economy", "premium_economy", "business"}

# Every chaos scenario this service can run. Pre-registered at 0 so the series
# always exists and the "Active Chaos Simulations" stat panel is never empty.
CHAOS_SCENARIOS = ("memory_leak",)


def normalise_route(origin: str | None, destination: str | None) -> str:
    """Collapse an arbitrary origin/destination pair into a bounded label value."""
    o = (origin or "ANY").upper()[:3]
    d = (destination or "ANY").upper()[:3]
    route = f"{o}-{d}"
    if route in KNOWN_ROUTES:
        return route
    if "ANY" in (o, d):
        return route if (o in {"DEL", "BOM", "BLR", "HYD", "GOI", "ANY"}) else "other"
    return "other"


def normalise_cabin_class(cabin_class: str | None) -> str:
    cc = (cabin_class or "economy").lower()
    return cc if cc in KNOWN_CABIN_CLASSES else "other"


# ---------------------------------------------------------------------------
# Business / RED metrics required by the SPOG dashboard
# ---------------------------------------------------------------------------
FLIGHT_SEARCH_REQUESTS = Counter(
    "flight_search_requests_total",
    "Flight search requests, dimensioned by route, cabin class and HTTP status.",
    ["route", "cabin_class", "status_code"],
)

FLIGHT_SEARCH_DURATION = Histogram(
    "flight_search_duration_seconds",
    "End-to-end flight search handler duration in seconds.",
    ["route", "cabin_class"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

FLIGHT_SEARCH_RESULTS = Histogram(
    "flight_search_results_returned",
    "Number of flights returned per search. The 0 bucket surfaces "
    "zero-result searches, which is a conversion-loss signal.",
    ["route"],
    buckets=(0, 1, 2, 5, 10, 25, 50),
)

FLIGHT_SEARCH_ZERO_RESULTS = Counter(
    "flight_search_zero_results_total",
    "Searches that returned no flights.",
    ["route", "cabin_class"],
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
    """Pre-create every chaos gauge child at 0 so panels render before first use."""
    for scenario in CHAOS_SCENARIOS:
        ACTIVE_CHAOS_SIMULATIONS.labels(scenario=scenario).set(0)
