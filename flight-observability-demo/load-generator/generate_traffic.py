#!/usr/bin/env python3
import requests
import random
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("traffic-generator")

# Point directly to services on Docker network (bypass nginx)
BOOKING_URL = "http://booking-service:8002"
SEARCH_URL = "http://flight-search-service:8001"

ROUTES = ["NYC-LAX", "LAX-NYC", "NYC-MIA", "MIA-NYC", "LAX-MIA"]
FLIGHTS_BY_ROUTE = {
    "NYC-LAX": ["FL100", "FL101"],
    "LAX-NYC": ["FL101", "FL102"],
    "NYC-MIA": ["FL102", "FL103"],
    "MIA-NYC": ["FL103", "FL104"],
    "LAX-MIA": ["FL104", "FL100"]
}

while True:
    try:
        route = random.choice(ROUTES)
        origin, destination = route.split("-")
        
        # Search
        resp = requests.get(f"{SEARCH_URL}/api/v1/search", params={"origin": origin, "destination": destination}, timeout=5)
        logger.info(f"🔍 SEARCH: {route} | Status: {resp.status_code}")
        time.sleep(random.uniform(0.5, 2))
        
        # Booking
        flight_id = random.choice(FLIGHTS_BY_ROUTE[route])
        resp = requests.post(
            f"{BOOKING_URL}/api/v1/bookings",
            json={"flight_id": flight_id, "passenger_name": f"User{random.randint(1000,9999)}", "amount": random.randint(200, 500)},
            timeout=10
        )
        logger.info(f"✅ BOOKING: {flight_id} | Status: {resp.status_code}")
        time.sleep(random.uniform(1, 3))
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        time.sleep(5)
