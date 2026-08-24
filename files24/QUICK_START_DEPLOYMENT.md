# ⚡ QUICK START - 5 MINUTE DEPLOYMENT

## 🎯 Goal
Deploy 7 production-grade observability components so Grafana dashboards show **REAL LIVE DATA** immediately.

---

## 📋 Pre-Deployment Checklist

```bash
# Verify you're in the right directory
cd /workspaces/flight-obs-demo/flight-observability-demo

# Verify docker works
docker compose ps
# Should show existing services (or empty if first run)
```

---

## 🚀 DEPLOYMENT (Copy-Paste These Commands)

### Step 1: Copy All 7 Components (2 min)

```bash
# Copy microservice code (COMPONENTS 1-3)
cp /mnt/user-data/outputs/COMPONENT_1_booking_app.py services/booking/app.py
cp /mnt/user-data/outputs/COMPONENT_2_payment_app.py services/payment/app.py
cp /mnt/user-data/outputs/COMPONENT_3_flight_search_app.py services/flight-search/app.py

# Copy Prometheus configs (COMPONENT 4-5)
cp /mnt/user-data/outputs/COMPONENT_4_recording_rules.yml prometheus/recording_rules.yml
cp /mnt/user-data/outputs/COMPONENT_5_prometheus.yml prometheus/prometheus.yml

# Copy traffic generator (COMPONENT 6)
cp /mnt/user-data/outputs/COMPONENT_6_traffic_generator.py load-generator/generate_traffic.py

# Copy orchestration (COMPONENT 7)
cp /mnt/user-data/outputs/COMPONENT_7_docker-compose.yml docker-compose.yml
```

### Step 2: Build & Deploy (2 min)

```bash
# Clean previous deployment (IMPORTANT!)
docker compose down -v

# Build fresh with new instrumentation
docker compose build --no-cache

# Start all services
docker compose up -d

# Wait for services to fully initialize
echo "⏳ Waiting for services... (40 seconds)"
sleep 40

# Verify all services are UP
docker compose ps
```

### Step 3: Validate Data Pipeline (1 min)

```bash
# Check 1: Services export metrics
echo "✅ Check 1: Metrics export"
curl -s http://localhost:8002/metrics | grep "booking_success_total" | head -1

# Check 2: Prometheus scrapes
echo "✅ Check 2: Prometheus targets"
curl -s http://localhost:9090/api/v1/targets | grep "\"state\":\"up\"" | wc -l
# Should show: 4 (booking, payment, flight-search, servicenow)

# Check 3: Traffic being generated
echo "✅ Check 3: Traffic generator"
docker logs load-generator | tail -3

# Check 4: Open Grafana
echo "✅ Check 4: Open browser"
echo "   URL: http://localhost:3000"
echo "   User: admin"
echo "   Pass: admin"
```

---

## 🎉 Success!

If all 4 checks pass:

1. Open **http://localhost:3000**
2. Login: `admin` / `admin`
3. Navigate to any dashboard
4. **ALL PANELS SHOW REAL LIVE DATA** ✅

---

## 📊 What You'll See

### Leadership L1 Executive Dashboard
- IT Health Score: 85-95 (green)
- Availability: 98-99.5%
- Booking Success Rate: 92-96%
- Revenue at Risk: ₹500-2000/hr
- P95 Latency: 50-150ms

### SRE S1 Ops & Observability
- Request Rate: 30-50 req/min
- Error Rate: 3-8%
- P95 Latency: 50-200ms
- Memory Usage: Trending upward
- Business Metrics: Bookings confirmed/failed

### All Panels
- ✅ Show non-zero values
- ✅ Have trend lines
- ✅ Update every 15-30 seconds
- ✅ Display realistic business metrics

---

## 🆘 Troubleshooting (If Something Breaks)

### Issue: "No Data" in dashboards

```bash
# Fix 1: Check if services are running
docker compose ps | grep -E "booking|payment|flight-search"
# Should all show "Up"

# Fix 2: Check if metrics exist
curl http://localhost:8002/metrics | grep booking_success_total
# Should return a counter value

# Fix 3: Rebuild everything
docker compose down -v
docker compose build --no-cache
docker compose up -d
sleep 40
```

### Issue: Services won't start

```bash
# Check service logs
docker logs booking-service
docker logs payment-service
docker logs flight-search-service

# Rebuild just that service
docker compose build --no-cache booking-service
docker compose up -d booking-service
```

### Issue: Prometheus shows "DOWN" targets

```bash
# Wait a bit longer (services take time to start)
sleep 30

# Restart Prometheus
docker compose restart prometheus

# Check if services are accessible from Prometheus container
docker exec prometheus curl http://booking-service:8002/health
```

---

## 📈 What Gets Deployed

| Component | What It Does | Result |
|-----------|------|--------|
| **Booking Service** | Exports metrics: booking_success_total, booking_failures_total, booking_value_* | ✅ Dashboards show booking trends |
| **Payment Service** | Exports metrics: payment_failures_total, payment_processing_duration_* | ✅ Dashboards show payment health |
| **Flight-Search** | Exports metrics: flight_search_requests_total | ✅ Dashboards show funnel metrics |
| **Prometheus Rules** | Creates derived metrics: spog:it_health_score, svc:availability:ratio5m | ✅ Dashboards show aggregated KPIs |
| **Prometheus Config** | Scrapes all services every 15 seconds | ✅ Metrics flow continuously |
| **Traffic Generator** | Makes 30-50 requests/minute continuously | ✅ Metrics never go stale |
| **Docker-Compose** | Orchestrates all services with health checks | ✅ Everything auto-starts in order |

---

## ✅ Expected Metrics

After 5 minutes, you should see:

```
booking_success_total          ≥ 5
booking_failures_total         ≥ 1
payment_failures_total         ≥ 1
flight_search_requests_total   ≥ 15
http_requests_total            ≥ 50
spog:it_health_score           80-95 (gauge)
svc:availability:ratio5m       0.92-0.98 (ratio)
```

---

## 🎯 Next Steps

### Immediate
- ✅ Open Grafana: http://localhost:3000
- ✅ Verify dashboards show data
- ✅ Explore all dashboard pages

### Testing
- Stop a service: `docker stop payment-service`
- Watch dashboards degrade (2-3 min)
- Restart: `docker start payment-service`
- Watch dashboards recover

### Production-Ready
- Add authentication (Okta, LDAP)
- Configure Alertmanager webhooks
- Set up persistent storage
- Add more scrape targets

---

## 📞 Support Commands

```bash
# Check all services
docker compose ps

# View logs (most recent 20 lines)
docker logs booking-service -n 20
docker logs load-generator -n 20

# Check metrics directly
curl http://localhost:8002/metrics
curl http://localhost:8003/metrics
curl http://localhost:8001/metrics

# Check Prometheus health
curl http://localhost:9090/api/v1/targets

# Restart everything
docker compose restart

# Full reset
docker compose down -v && docker compose up -d
```

---

## ✨ Key Points

- ✅ **NO dashboard modifications** - only backend fixes
- ✅ **Zero manual traffic generation** - continuous load generator
- ✅ **REAL metrics** - not mocks or fake data
- ✅ **Live trending** - dashboards update every 15-30 seconds
- ✅ **Production-ready** - proper instrumentation, error handling, logging

---

## 🎊 DONE!

You now have a **FULLY FUNCTIONAL OBSERVABILITY PIPELINE** with:
- ✅ Real microservices instrumentation
- ✅ Prometheus metrics collection
- ✅ Grafana dashboards with live data
- ✅ OpenTelemetry distributed tracing
- ✅ Continuous synthetic workload
- ✅ Structured logging with trace context

**Enjoy your dashboards!** 🚀
