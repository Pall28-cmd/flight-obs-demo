# Flight Booking Microservices — Observability Prototype

A fully functional local prototype demonstrating end-to-end **Observability**
(Metrics, Logs, Traces) using **Prometheus, Grafana, Jaeger, Loki, and
OpenTelemetry** — built to support the *SRE & AIOps Strategy Report*
(Observability pillar, Section 4).

Every chaos scenario in this app is deliberately mapped to a real pattern
found in the 2,000-ticket historical analysis, so triggering chaos here is a
live demonstration of the report's findings, not a generic textbook demo.

## Architecture

```
                        ┌─────────────────┐
   Browser  ──────────► │  NGINX Gateway   │  :8000  (frontend + API proxy)
                        └────────┬────────┘
                                 │
        ┌────────────────────────┼─────────────────────────┐
        ▼                        ▼                          ▼
┌───────────────┐       ┌────────────────┐         ┌─────────────────┐
│ Flight Search │       │ Booking &      │  calls  │ Payment Gateway │
│ Service :8001 │       │ Inventory :8002├────────►│ Service :8003   │
└───────────────┘       └────────────────┘         └─────────────────┘
        │                        │                          │
        └────────────┬───────────┴──────────────┬───────────┘
                      ▼                          ▼
              OpenTelemetry Collector      /metrics (Prometheus scrape)
                      │
                      ▼
                   Jaeger  ◄── traces        Prometheus ◄── metrics
                                                   │
                                             Alertmanager
     stdout JSON logs ──► Promtail ──► Loki ◄──────┘
                                          │
                                          ▼
                                       Grafana :3000
                              (Prometheus + Loki + Jaeger datasources,
                               pre-provisioned dashboard)
```

## Prerequisites

- Docker and Docker Compose installed
- ~4GB RAM free, ports 3000, 3100, 4317, 4318, 8000-8003, 9090, 9093, 16686 available

## Quickstart

```bash
cd flight-observability-demo
docker-compose up --build
```

First build takes a few minutes (pulling Python base images + observability
stack images). Once running:

| Tool | URL | Notes |
|---|---|---|
| **Frontend / App** | http://localhost:8000 | Search flights, book, trigger chaos |
| **Grafana** | http://localhost:3000 | Login `admin` / `admin` (or anonymous access is enabled) |
| **Prometheus** | http://localhost:9090 | Raw metrics + Alerts tab |
| **Jaeger** | http://localhost:16686 | Distributed traces — select service, click a trace |
| **Alertmanager** | http://localhost:9093 | Alert routing status |

A background **load generator** starts automatically and continuously
searches/books flights so Grafana panels have live data from the moment you
open them — you don't need to click anything first.

The Grafana dashboard **"Flight Booking — Observability Dashboard"** is
pre-provisioned and appears on first login (Dashboards → Browse).

## Using the app manually

1. Open http://localhost:8000
2. Search flights (e.g. origin `DEL`)
3. Book a flight — this triggers a real cross-service call chain:
   `NGINX → booking-service → payment-service`, fully traced.
4. Open Jaeger, search for service `booking-service`, and click a recent
   trace — you'll see the full span tree across all three services with a
   single shared `trace_id`.
5. Open Grafana and watch the RED metrics (Rate/Errors/Duration) update.

## Triggering Chaos Scenarios

Each chaos scenario has a Start/Stop button on the frontend, or you can
trigger via curl. **Each one mirrors a specific finding from the strategy
report** — this is the core of the demo.

### 1. Memory Leak → mirrors Gap G-01 (Web Proxy resource exhaustion, 78 tickets)

```bash
curl -X POST http://localhost:8000/api/chaos/flight-search/memory-leak/start
# watch Grafana panel "Flight Search Memory Usage" climb, and the
# FlightSearchHighMemory alert go from inactive -> pending -> firing
# in Prometheus (http://localhost:9090/alerts)
curl -X POST http://localhost:8000/api/chaos/flight-search/memory-leak/stop
```

### 2. Error Spike → mirrors Active Directory auth-cascade / downstream failure pattern

```bash
curl -X POST http://localhost:8000/api/chaos/booking/error-spike/start
# ~50% of booking requests now return HTTP 500
# watch the "Error Rate by Service" panel spike and the
# HighBookingErrorRate alert fire
curl -X POST http://localhost:8000/api/chaos/booking/error-spike/stop
```

### 3. Payment Latency → mirrors leading-indicator pattern P-01 (82% confidence)

```bash
curl -X POST http://localhost:8000/api/chaos/payment/latency/start
# every payment now takes 3-5s
# watch "Payment Processing Duration (P95)" spike and the
# PaymentServiceHighLatency alert fire
curl -X POST http://localhost:8000/api/chaos/payment/latency/stop
```

### Watching the full story unfold

1. Trigger a chaos scenario (button or curl above).
2. **Prometheus** (`/alerts`): watch the corresponding alert move from
   Inactive → Pending → Firing.
3. **Grafana**: watch the relevant panel move in real time (5s refresh).
4. **Jaeger**: find a slow/failed trace and inspect the span breakdown to
   see exactly where the fault occurred.
5. **Grafana Logs panel**: filter/search the live JSON logs — every log
   line carries the same `trace_id` as the trace you just inspected, so you
   can pivot from a dashboard alert straight to the exact log lines and
   trace for that incident.
6. Stop the chaos scenario and watch the system recover.

This end-to-end loop (alert → dashboard → trace → correlated logs) is
exactly the "single pane of glass" investigative workflow described in
Section 5 of the strategy report, and the memory/error/latency scenarios are
exactly the automation candidates described in Sections 2 and 3.

## What's instrumented

- **Traces**: OpenTelemetry auto-instrumentation (FastAPI + Requests) on all
  three services, exported via OTLP to the OTel Collector, forwarded to
  Jaeger. Trace context propagates automatically across the
  booking → payment HTTP call.
- **Metrics**: every service exposes `/metrics` in Prometheus format —
  standard RED metrics (`http_requests_total`,
  `http_request_duration_seconds`) plus business metrics
  (`flight_bookings_total`, `payment_failures_total`,
  `payment_processing_duration_seconds`, `flight_search_total`).
- **Logs**: structured JSON to stdout on every request, containing
  `timestamp`, `log_level`, `service_name`, `message`, `trace_id`, `span_id`.
  Collected by Promtail from Docker container logs, shipped to Loki, queried
  in Grafana.
- **Alerts**: three Prometheus alerting rules (`HighBookingErrorRate`,
  `PaymentServiceHighLatency`, `FlightSearchHighMemory`), routed through
  Alertmanager.

## Stopping / cleaning up

```bash
docker-compose down          # stop everything
docker-compose down -v       # also remove volumes (Loki/Prometheus data)
```

## Troubleshooting

- **Grafana shows "no data"**: give the load-generator ~30s to warm up, or
  book a flight manually from the frontend.
- **Loki logs panel empty**: Promtail needs Docker socket access
  (`/var/run/docker.sock`) — this only works on Linux/macOS Docker Desktop
  hosts, not in restricted CI sandboxes.
- **Jaeger shows no traces**: confirm `otel-collector` and `jaeger`
  containers are both healthy (`docker-compose ps`); traces are batched
  every 2s so allow a few seconds after a request.
- **Port conflicts**: if 3000/8000/9090 etc. are already in use locally,
  edit the `ports:` mappings in `docker-compose.yml` (left side is the host
  port).

## Extending this for the strategy report

- Add the remaining two autohealing candidates (Active Directory, Database
  Replication) as additional services/chaos scenarios if you want full
  parity with Section 2's five candidates.
- Add a `/api/v1/chaos/status` sweep endpoint or Grafana annotation webhook
  so chaos start/stop events are automatically annotated on the timeseries
  panels — makes screenshots for the report self-explanatory.
- Point Grafana's alert notification channel at Slack/Teams for a live demo
  of the "single pane of glass → alert → action" loop described in
  Section 5.
