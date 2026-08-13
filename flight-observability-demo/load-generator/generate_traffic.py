import random
import time

import requests

BASE_URL = "http://nginx-gateway:8000"
ORIGINS = ["DEL", "BOM", "BLR", ""]
FLIGHT_IDS = ["FL100", "FL101", "FL102", "FL103", "FL104"]
NAMES = ["Priya Sharma", "Rohan Gupta", "Aisha Khan", "Vikram Rao", "Sneha Iyer"]


def run():
    print("load-generator: starting continuous background traffic...")
    while True:
        try:
            origin = random.choice(ORIGINS)
            params = {"origin": origin} if origin else {}
            requests.get(f"{BASE_URL}/api/flights/search", params=params, timeout=5)

            if random.random() < 0.4:
                flight_id = random.choice(FLIGHT_IDS)
                requests.post(
                    f"{BASE_URL}/api/bookings",
                    json={
                        "flight_id": flight_id,
                        "passenger_name": random.choice(NAMES),
                        "amount": random.randint(3000, 7000),
                    },
                    timeout=15,
                )
        except Exception as e:
            print(f"load-generator: request error - {e}")
        time.sleep(random.uniform(0.5, 2.0))


if __name__ == "__main__":
    run()
