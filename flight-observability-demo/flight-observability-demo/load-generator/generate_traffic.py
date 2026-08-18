"""
Background traffic generator.

Extended for the SPOG dashboard: the new metrics carry `route`, `cabin_class`
and `payment_method` labels, and those panels are empty unless traffic actually
varies along those dimensions. Weights below are deliberately uneven so the
dashboard shows a realistic distribution rather than a flat one -- a flat
distribution makes topk() and "by method" panels look broken.
"""

import random
import time

import requests

BASE_URL = "http://nginx-gateway:8000"

# Origin/destination pairs that exist in the flight catalogue, plus a couple of
# misses so `flight_search_zero_results_total` and the "Search fill rate" KPI
# have something to report.
SEARCH_PAIRS = [
    ("DEL", "BOM", 0.28),
    ("DEL", "BLR", 0.20),
    ("BOM", "DEL", 0.16),
    ("BLR", "HYD", 0.12),
    ("DEL", "GOI", 0.10),
    ("DEL", None, 0.08),   # origin-only search -> route DEL-ANY
    ("HYD", "COK", 0.04),  # no such flight -> zero results
    (None, None, 0.02),    # browse-all
]

FLIGHT_IDS = ["FL100", "FL101", "FL102", "FL103", "FL104"]

CABIN_CLASSES = [("economy", 0.72), ("premium_economy", 0.19), ("business", 0.09)]

# UPI-heavy, as you would expect for an Indian booking flow.
PAYMENT_METHODS = [
    ("upi", 0.42),
    ("credit_card", 0.26),
    ("debit_card", 0.16),
    ("netbanking", 0.10),
    ("wallet", 0.06),
]


def weighted(choices):
    """choices: list of (value, weight) or (a, b, weight) tuples."""
    population = [c[:-1] if len(c) > 2 else c[0] for c in choices]
    weights = [c[-1] for c in choices]
    return random.choices(population, weights=weights)[0]


def run():
    print("load-generator: starting continuous background traffic...", flush=True)
    while True:
        try:
            # ---- Search -------------------------------------------------
            origin, destination = weighted(SEARCH_PAIRS)
            cabin = weighted(CABIN_CLASSES)
            params = {"cabin_class": cabin}
            if origin:
                params["origin"] = origin
            if destination:
                params["destination"] = destination
            requests.get(f"{BASE_URL}/api/flights/search", params=params, timeout=5)

            # ---- Book (roughly 40% of searches convert to an attempt) ----
            if random.random() < 0.40:
                requests.post(
                    f"{BASE_URL}/api/bookings",
                    json={
                        "flight_id": random.choice(FLIGHT_IDS),
                        "passenger_name": random.choice(
                            ["Priya Sharma", "Rohan Gupta", "Aisha Khan",
                             "Vikram Rao", "Sneha Iyer"]
                        ),
                        # Fare varies by cabin so booking_value_inr_total and the
                        # revenue panels show a believable spread.
                        "amount": {
                            "economy": random.randint(3000, 6000),
                            "premium_economy": random.randint(6000, 11000),
                            "business": random.randint(11000, 24000),
                        }[cabin],
                        "cabin_class": cabin,
                        "payment_method": weighted(PAYMENT_METHODS),
                    },
                    timeout=15,
                )
        except Exception as e:
            print(f"load-generator: request error - {e}", flush=True)
        time.sleep(random.uniform(0.5, 2.0))


if __name__ == "__main__":
    run()
