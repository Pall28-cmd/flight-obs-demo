#!/usr/bin/env python3
"""
Continuous Traffic Generator for Flight Booking Demo
Generates realistic synthetic workload across all microservices
Ensures metrics stream continuously to Grafana dashboards
"""

import requests
import random
import time
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("traffic-generator")

# ============================================================================
# CONFIGURATION
# ============================================================================

# Services accessible via nginx gateway
BASE_URL = "http://nginx-gateway:8000"

# Fallback to localhost if running locally
try:
    response = requests.get(BASE_URL + "/health", timeout=2)
except:
    BASE_URL = "http://localhost:8000"
    logger.warning(f"Using fallback URL: {BASE_URL}")

# Test data
ROUTES = ["NYC-LAX", "LAX-NYC", "NYC-MIA", "MIA-NYC", "LAX-MIA"]
FLIGHTS_BY_ROUTE = {
    "NYC-LAX": ["FL100", "FL101"],
    "LAX-NYC": ["FL101", "FL102"],
    "NYC-MIA": ["FL102", "FL103"],
    "MIA-NYC": ["FL103", "FL104"],
    "LAX-MIA": ["FL104", "FL100"]
}
PAYMENT_METHODS = ["credit_card", "debit_card", "digital_wallet", "bank_transfer"]
CABIN_CLASSES = ["economy", "business", "first"]

# ============================================================================
# TRAFFIC GENERATION FUNCTIONS
# ============================================================================

def generate_search_request():
    """Generate a search request - feeds flight_search_requests_total metric"""
    try:
        route = random.choice(ROUTES)
        origin, destination = route.split("-")
        
        response = requests.get(
            f"{BASE_URL}/api/v1/search",
            params={"origin": origin, "destination": destination},
            timeout=5
        )
        
        if response.status_code == 200:
            logger.info(f"🔍 SEARCH: {route} | Status: {response.status_code}")
            return True
        else:
            logger.warning(f"⚠️  SEARCH failed: {route} | Status: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ SEARCH error: {e}")
        return False


def generate_booking_request():
    """Generate a booking request - feeds all booking_* metrics"""
    try:
        route = random.choice(ROUTES)
        flight_id = random.choice(FLIGHTS_BY_ROUTE[route])
        payment_method = random.choice(PAYMENT_METHODS)
        cabin_class = random.choice(CABIN_CLASSES)
        amount = random.randint(200, 800)
        
        payload = {
            "flight_id": flight_id,
            "passenger_name": f"Passenger{random.randint(10000, 99999)}",
            "payment_method": payment_method,
            "cabin_class": cabin_class,
            "amount": amount
        }
        
        response = requests.post(
            f"{BASE_URL}/api/v1/bookings",
            json=payload,
            timeout=10
        )
        
        status = response.status_code
        if status == 201:
            logger.info(f"✅ BOOKING: {flight_id} | {payment_method} | ₹{amount} | Status: {status}")
            return True
        elif status == 409:
            logger.warning(f"⚠️  BOOKING: No seats for {flight_id} | Status: {status}")
            return True  # Still valid for metrics
        elif status == 402:
            logger.warning(f"⚠️  BOOKING: Payment declined | Status: {status}")
            return True  # Still valid for metrics
        else:
            logger.warning(f"⚠️  BOOKING failed: {flight_id} | Status: {status}")
            return False
            
    except Exception as e:
        logger.error(f"❌ BOOKING error: {e}")
        return False


def generate_health_check():
    """Health checks - minimal traffic, keeps services alive"""
    try:
        services = [
            f"{BASE_URL}/health",
            "http://booking-service:8002/health",
            "http://payment-service:8003/health",
            "http://flight-search-service:8001/health"
        ]
        
        for service_url in services:
            try:
                response = requests.get(service_url, timeout=2)
                if response.status_code == 200:
                    service_name = service_url.split("/")[2].split(":")[0]
                    logger.debug(f"❤️  {service_name} is healthy")
            except:
                pass
                
    except Exception as e:
        logger.debug(f"Health check error: {e}")


# ============================================================================
# MAIN TRAFFIC GENERATION LOOP
# ============================================================================

def main():
    """Continuous traffic generation loop"""
    
    logger.info("=" * 70)
    logger.info("🚀 FLIGHT BOOKING TRAFFIC GENERATOR STARTED")
    logger.info("=" * 70)
    logger.info(f"Base URL: {BASE_URL}")
    logger.info(f"Target Routes: {ROUTES}")
    logger.info("")
    
    request_count = 0
    success_count = 0
    
    while True:
        try:
            # Pattern: 3 searches, then 1 booking (realistic user funnel)
            # This ensures proper funnel metrics
            
            # 3 search requests
            for i in range(3):
                if generate_search_request():
                    success_count += 1
                request_count += 1
                time.sleep(random.uniform(0.3, 0.8))
            
            # 1 booking request
            if generate_booking_request():
                success_count += 1
            request_count += 1
            
            # Health check occasionally
            if request_count % 10 == 0:
                generate_health_check()
            
            # Wait before next cycle (2-5 seconds)
            wait_time = random.uniform(2, 5)
            time.sleep(wait_time)
            
            # Log statistics every 100 requests
            if request_count % 100 == 0:
                success_rate = (success_count / request_count) * 100
                logger.info(f"📊 STATS: {request_count} requests | {success_rate:.1f}% success rate")
            
        except KeyboardInterrupt:
            logger.info("⏹️  Traffic generator stopped by user")
            break
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            logger.info("Restarting traffic generation in 5 seconds...")
            time.sleep(5)
    
    logger.info("=" * 70)
    logger.info("🛑 TRAFFIC GENERATOR STOPPED")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
