# PromQL & LogQL Verification Guide

Every query used by **Flight Booking — Digital Operations Command Center** (`uid: flight-booking-spog`), extracted directly from the dashboard JSON.

This file is generated. If you change a panel query, regenerate it rather than editing here.

## How to use this

Prometheus expression browser: <http://localhost:9090/graph>  
Grafana Explore: <http://localhost:3000/explore>

Dashboard variables have been replaced with concrete values so every query below is directly copy-pasteable:

| Variable | Substituted with |
|---|---|
| `$environment` | `dev` |
| `$service` (All) | `flight-search-service\|booking-service\|payment-service` |
| `$route` (All) | `.*` |
| `$payment_method` (All) | `.*` |
| `$log_level` (default) | `WARNING\|ERROR` |
| `$rate_window` | `5m` |
| `$__range` | `1h` |
| `$__interval` / `$__auto` | `1m` |

---

## Step 0 — preflight checks

Run these first. If any fails, no panel below will work.

```promql
# 1. All three targets up, and carrying the service_name/environment target
#    labels that every dashboard variable depends on.
up{job=~".*-service"}

# 2. Confirm the target labels actually landed. Expect service_name,
#    environment, tier and business_service on every series.
count by (service_name, environment, tier, business_service) (up)

# 3. CRITICAL: confirm the histogram le boundaries the Apdex recording rule
#    matches on. You MUST see "0.25" and "1.0" literally in the output.
#    If your client library formats them as "0.250000" or "1", edit
#    svc:apdex:ratio5m in prometheus/recording_rules.yml to match.
count by (le) (http_request_duration_seconds_bucket)

# 4. Confirm the new custom metrics exist at all.
count by (__name__) ({__name__=~"flight_search_.*|booking_.*|payment_.*|active_chaos_.*"})

# 5. Confirm the recording rules have evaluated (empty = rules not loaded;
#    check Status > Rules in the Prometheus UI).
count by (__name__) ({__name__=~"svc:.*|slo:.*|biz:.*|spog:.*"})
```

Shell one-liners for the same checks:

```bash
# Raw exposition from each service
curl -s localhost:8001/metrics | grep -E '^flight_search_requests_total'
curl -s localhost:8002/metrics | grep -E '^booking_(success|requests|failure)_total'
curl -s localhost:8003/metrics | grep -E '^payment_(gateway_latency_seconds_bucket|transactions_total)'
curl -s localhost:8001/metrics | grep -E '^active_chaos_simulations'

# Prometheus target health and rule health
curl -s localhost:9090/api/v1/targets | python3 -m json.tool | grep -E 'health|service_name'
curl -s localhost:9090/api/v1/rules  | python3 -m json.tool | grep -E '"name"|"health"'

# Loki label check -- the environment label must be present or every Loki
# panel returns nothing
curl -s 'localhost:3100/loki/api/v1/labels'
curl -s 'localhost:3100/loki/api/v1/label/service/values'
curl -s 'localhost:3100/loki/api/v1/label/environment/values'
```

---

## Recording rules

Defined in `prometheus/recording_rules.yml`. The Leadership panels read these rather than inlining the expressions, so a KPI definition lives in exactly one place. Query the rule name directly to test it; query the `expr` to test the definition.

### group `spog_service_sli` (interval 15s)

**`svc:http_requests:rate5m`**

```promql
sum by (environment, service_name) (rate(http_requests_total[5m]))
```

**`svc:http_errors:rate5m`**

```promql
sum by (environment, service_name) (rate(http_requests_total{status=~"5.."}[5m]))
```

**`svc:availability:ratio5m`**

```promql
1 - ( svc:http_errors:rate5m / clamp_min(svc:http_requests:rate5m, 0.001) )
```

**`svc:latency_p50:seconds5m`**

```promql
histogram_quantile(0.50, sum by (environment, service_name, le) (rate(http_request_duration_seconds_bucket[5m])) )
```

**`svc:latency_p95:seconds5m`**

```promql
histogram_quantile(0.95, sum by (environment, service_name, le) (rate(http_request_duration_seconds_bucket[5m])) )
```

**`svc:latency_p99:seconds5m`**

```promql
histogram_quantile(0.99, sum by (environment, service_name, le) (rate(http_request_duration_seconds_bucket[5m])) )
```

**`svc:apdex:ratio5m`**

```promql
( sum by (environment, service_name) (rate(http_request_duration_seconds_bucket{le="0.25"}[5m])) + sum by (environment, service_name) (rate(http_request_duration_seconds_bucket{le="1.0"}[5m])) ) / (2 * clamp_min( sum by (environment, service_name) (rate(http_request_duration_seconds_count[5m])), 0.001 ))
```

### group `spog_slo` (interval 30s)

**`slo:error_budget_burn_rate:ratio1h`**

```promql
( sum by (environment, service_name) (rate(http_requests_total{status=~"5.."}[1h])) / clamp_min(sum by (environment, service_name) (rate(http_requests_total[1h])), 0.001) ) / 0.005
```

**`slo:error_budget_remaining:ratio30d`**

```promql
clamp_min( 1 - ( ( sum by (environment, service_name) (increase(http_requests_total{status=~"5.."}[30d])) / clamp_min(sum by (environment, service_name) (increase(http_requests_total[30d])), 1) ) / 0.005 ), 0)
```

### group `spog_business` (interval 15s)

**`biz:flight_searches:rate5m`**

```promql
sum by (environment) (rate(flight_search_requests_total[5m]))
```

**`biz:booking_attempts:rate5m`**

```promql
sum by (environment) (rate(booking_requests_total[5m]))
```

**`biz:bookings_confirmed:rate5m`**

```promql
sum by (environment) (rate(booking_success_total[5m]))
```

**`biz:booking_success:ratio5m`**

```promql
biz:bookings_confirmed:rate5m / clamp_min(biz:booking_attempts:rate5m, 0.001)
```

**`biz:search_to_book:ratio5m`**

```promql
biz:bookings_confirmed:rate5m / clamp_min(biz:flight_searches:rate5m, 0.001)
```

**`biz:revenue_inr:rate5m`**

```promql
sum by (environment) (rate(booking_value_inr_total[5m]))
```

**`biz:revenue_at_risk_inr:rate5m`**

```promql
sum by (environment) (rate(booking_value_at_risk_inr_total[5m]))
```

**`biz:payment_success:ratio5m`**

```promql
sum by (environment) (rate(payment_transactions_total{status="success"}[5m])) / clamp_min(sum by (environment) (rate(payment_transactions_total[5m])), 0.001)
```

**`biz:payment_gateway_p95:seconds5m`**

```promql
histogram_quantile(0.95, sum by (environment, le) (rate(payment_gateway_latency_seconds_bucket[5m])) )
```

### group `spog_composite` (interval 30s)

**`spog:it_health_score`**

```promql
100 * ( 0.4 * avg by (environment) (svc:availability:ratio5m) + 0.3 * avg by (environment) (svc:apdex:ratio5m) + 0.3 * biz:booking_success:ratio5m )
```

---

## Panel queries by dashboard row

## LEADERSHIP  ·  Executive Summary

> Maps to Power BI wireframe page L1 (Executive & Governance). Decision supported: is the estate healthy enough to leave alone this hour?

### IT Health Score

`gauge` · none

> Composite: 40% availability + 30% Apdex + 30% booking success. Defined once in prometheus/recording_rules.yml (spog:it_health_score). Weights are provisional -- agree them with service owners before this goes in front of leadership.

**A** · `prometheus` · legend `health score`

```promql
spog:it_health_score{environment="dev"}
```

### Availability (5m)

`stat` · percent

> 1 - (5xx rate / total rate), averaged across the selected services. SLO target 99.5%.

**A** · `prometheus` · legend `availability`

```promql
100 * avg(svc:availability:ratio5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"})
```

### Booking Success Rate (5m)

`stat` · percent

> Confirmed bookings over all booking attempts. Raw PromQL rather than the biz:booking_success:ratio5m recording rule so the $route and $payment_method variables still filter it.

**A** · `prometheus` · legend `success rate`

```promql
100 * sum(rate(booking_success_total{environment="dev", route=~".*", payment_method=~".*"}[5m]))
  / clamp_min(sum(rate(booking_requests_total{environment="dev", route=~".*", payment_method=~".*"}[5m])), 0.001)
```

### Search → Book Conversion

`stat` · percent

> Funnel conversion from search to confirmed booking. A drop here with availability still green points at a business or UX problem, not an outage.

**A** · `prometheus` · legend `conversion`

```promql
100 * sum(rate(booking_success_total{environment="dev", route=~".*", payment_method=~".*"}[5m]))
  / clamp_min(sum(rate(flight_search_requests_total{environment="dev", route=~".*"}[5m])), 0.001)
```

### Worst P95 Latency

`stat` · s

> Slowest service P95 across the selection -- deliberately max() not avg(), so one degraded service cannot be averaged out of view.

**A** · `prometheus` · legend `p95`

```promql
max(svc:latency_p95:seconds5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"})
```

### Revenue at Risk (₹/hr)

`stat` · currencyINR

> Annualised-to-hourly INR value of booking attempts that failed. Sourced from booking_value_at_risk_inr_total, incremented with the attempted amount on every failed booking.

**A** · `prometheus` · legend `at risk`

```promql
3600 * sum(rate(booking_value_at_risk_inr_total{environment="dev", route=~".*", payment_method=~".*"}[5m]))
```

## LEADERSHIP  ·  Business Service Health & Impact

> Maps to wireframe panels 'Business service health & coverage', 'Value delivered' and 'Business KPI & transaction impact'.

### Business Service Health — RAG over time

`state-timeline` · percentunit

> Grafana equivalent of the wireframe RAG heatmap, with time added. Green ≥99.5%, amber ≥99%, red below, grey = no telemetry.

**A** · `prometheus` · legend `{{service_name}}`

```promql
svc:availability:ratio5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

### Booking Funnel (5m rate)

`bargauge` · reqps

> Drop-off between the three stages is the conversion-loss story. Stage 1 is not filtered by $payment_method because payment method is not known at search time.

**A** · `prometheus` · legend `1 · Searches /s`

```promql
sum(rate(flight_search_requests_total{environment="dev", route=~".*"}[5m]))
```

**B** · `prometheus` · legend `2 · Booking attempts /s`

```promql
sum(rate(booking_requests_total{environment="dev", route=~".*", payment_method=~".*"}[5m]))
```

**C** · `prometheus` · legend `3 · Confirmed /s`

```promql
sum(rate(booking_success_total{environment="dev", route=~".*", payment_method=~".*"}[5m]))
```

### Revenue vs Revenue at Risk (₹/min)

`timeseries` · currencyINR

> Business-value view of reliability. Widening red band = failures are landing on high-value bookings.

**A** · `prometheus` · legend `Revenue realised`

```promql
60 * sum(rate(booking_value_inr_total{environment="dev", route=~".*", payment_method=~".*"}[5m]))
```

**B** · `prometheus` · legend `Revenue at risk`

```promql
60 * sum(rate(booking_value_at_risk_inr_total{environment="dev", route=~".*", payment_method=~".*"}[5m]))
```

### Business KPI & Transaction Impact

`table`

> Wireframe 'Business KPI & transaction impact' table. Rows are named by each query's legendFormat, then collapsed with a reduce/lastNotNull transformation -- the standard Grafana pattern for a KPI list.

**A** · `prometheus` · instant · legend `Booking success rate %`

```promql
100 * sum(rate(booking_success_total{environment="dev", route=~".*", payment_method=~".*"}[5m])) / clamp_min(sum(rate(booking_requests_total{environment="dev", route=~".*", payment_method=~".*"}[5m])), 0.001)
```

**B** · `prometheus` · instant · legend `Payment success rate %`

```promql
100 * sum(rate(payment_transactions_total{environment="dev", payment_method=~".*", status="success"}[5m])) / clamp_min(sum(rate(payment_transactions_total{environment="dev", payment_method=~".*"}[5m])), 0.001)
```

**C** · `prometheus` · instant · legend `Search fill rate %`

```promql
100 * (1 - (sum(rate(flight_search_zero_results_total{environment="dev", route=~".*"}[5m])) / clamp_min(sum(rate(flight_search_requests_total{environment="dev", route=~".*"}[5m])), 0.001)))
```

**D** · `prometheus` · instant · legend `Confirmed bookings (range)`

```promql
sum(increase(booking_success_total{environment="dev", route=~".*", payment_method=~".*"}[1h]))
```

**E** · `prometheus` · instant · legend `Failed bookings (range)`

```promql
sum(increase(booking_failure_total{environment="dev", route=~".*", payment_method=~".*"}[1h]))
```

**F** · `prometheus` · instant · legend `Booking value ₹ (range)`

```promql
sum(increase(booking_value_inr_total{environment="dev", route=~".*", payment_method=~".*"}[1h]))
```

**G** · `prometheus` · instant · legend `Value at risk ₹ (range)`

```promql
sum(increase(booking_value_at_risk_inr_total{environment="dev", route=~".*", payment_method=~".*"}[1h]))
```

### Booking Outcome Mix (selected range)

`piechart` · short

> Confirmed versus each canonical failure reason. Failure reasons are whitelisted in the app so this legend can never explode.

**A** · `prometheus` · legend `Confirmed`

```promql
sum(increase(booking_success_total{environment="dev", route=~".*", payment_method=~".*"}[1h]))
```

**B** · `prometheus` · legend `Failed — {{reason}}`

```promql
sum by (reason) (increase(booking_failure_total{environment="dev", route=~".*", payment_method=~".*"}[1h]))
```

### Top Routes by Confirmed Bookings

`barchart` · short

> topk(5) keeps this readable as the route catalogue grows.

**A** · `prometheus` · instant · format=table

```promql
topk(5, sum by (route) (increase(booking_success_total{environment="dev", route=~".*", payment_method=~".*"}[1h])))
```

## LEADERSHIP  ·  Live Operations Status

> Maps to wireframe page L3. Decision supported: is anything down right now, and is it already being handled?

### Services Up

`stat` · none

> Scrape health. A target that stops responding shows here before any application metric can tell you.

**A** · `prometheus` · legend `up`

```promql
sum(up{environment="dev", job=~".*-service"})
```

**B** · `prometheus` · legend `total`

```promql
count(up{environment="dev", job=~".*-service"})
```

### Targets Down

`stat` · none

> `or vector(0)` keeps the panel green instead of showing NO DATA when nothing is down -- count() over an empty set returns no series.

**A** · `prometheus` · legend `down`

```promql
count(up{environment="dev", job=~".*-service"} == 0) or vector(0)
```

### Active Chaos Simulations

`stat` · none

> Guards against misreading an intentional experiment as a real incident. Query B names the active scenario(s).

**A** · `prometheus` · legend `active`

```promql
sum(active_chaos_simulations{environment="dev"})
```

**B** · `prometheus` · legend `{{scenario}}`

```promql
sum by (scenario) (active_chaos_simulations{environment="dev"}) > 0
```

### Estate Error Rate (5m)

`stat` · percent

> 5xx share of all requests across the selected services.

**A** · `prometheus` · legend `error rate`

```promql
100 * sum(svc:http_errors:rate5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}) / clamp_min(sum(svc:http_requests:rate5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}), 0.001)
```

### ERROR Logs (5m)

`stat` · none

> Loki-sourced. `| __error__=""` drops non-JSON lines from sidecar containers so the count is not inflated by parse failures.

**A** · `loki` · legend `errors`

```logql
sum(count_over_time({environment="dev", service=~"flight-search-service|booking-service|payment-service"}
  | json | __error__="" | log_level="ERROR" [5m]))
```

### Payment Gateway

`stat` · none

> Single most important dependency for revenue. min() so any unhealthy gateway shows as DOWN.

**A** · `prometheus` · legend `gateway`

```promql
min(payment_gateway_up{environment="dev"})
```

### Live Service Status

`table`

> One row per service, five instant queries joined on service_name. This is the Grafana analogue of the wireframe's leadership status table.

**A** · `prometheus` · instant · format=table

```promql
svc:availability:ratio5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

**B** · `prometheus` · instant · format=table

```promql
svc:latency_p95:seconds5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

**C** · `prometheus` · instant · format=table

```promql
svc:http_requests:rate5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

**D** · `prometheus` · instant · format=table

```promql
svc:http_errors:rate5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

**E** · `prometheus` · instant · format=table

```promql
svc:apdex:ratio5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

### Critical Error Stream (trace-correlated)

`logs`

> WARNING and ERROR only, reformatted for scanning. Every line carries trace_id -- click a line, then follow the trace_id derived field into Jaeger for the full request waterfall.

**A** · `loki`

```logql
{environment="dev", service=~"flight-search-service|booking-service|payment-service"}
  | json | __error__=""
  | log_level=~"WARNING|ERROR"
  | line_format "[{{.service_name}}] {{.log_level}} {{.message}}  trace={{.trace_id}}"
```

## SRE  ·  Golden Signals (Traffic · Latency · Errors · Saturation)

> Maps to wireframe page S1. Decision supported: what is degrading, and how much error budget is left to spend on it?

### Traffic — requests/sec by service

`timeseries` · reqps

> RED: Rate. $rate_window controls the smoothing window; widen it on long time ranges to avoid sawtooth artefacts.

**A** · `prometheus` · legend `{{service_name}}`

```promql
sum by (service_name) (rate(http_requests_total{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}[5m]))
```

### Latency — P50 / P95 / P99

`timeseries` · s

> RED: Duration. Quantiles are computed after summing buckets by le -- never average a pre-computed quantile across services.

**A** · `prometheus` · legend `p50 {{service_name}}`

```promql
histogram_quantile(0.50, sum by (service_name, le) (rate(http_request_duration_seconds_bucket{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}[5m])))
```

**B** · `prometheus` · legend `p95 {{service_name}}`

```promql
histogram_quantile(0.95, sum by (service_name, le) (rate(http_request_duration_seconds_bucket{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}[5m])))
```

**C** · `prometheus` · legend `p99 {{service_name}}`

```promql
histogram_quantile(0.99, sum by (service_name, le) (rate(http_request_duration_seconds_bucket{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}[5m])))
```

### Errors — 5xx/sec and error ratio

`timeseries` · reqps

> RED: Errors. Absolute rate on the left axis, ratio on the right -- a low ratio at high traffic is a very different page than the reverse.

**A** · `prometheus` · legend `5xx/s {{service_name}}`

```promql
sum by (service_name) (rate(http_requests_total{environment="dev", service_name=~"flight-search-service|booking-service|payment-service", status=~"5.."}[5m]))
```

**B** · `prometheus` · legend `ratio {{service_name}}`

```promql
sum by (service_name) (rate(http_requests_total{environment="dev", service_name=~"flight-search-service|booking-service|payment-service", status=~"5.."}[5m])) / clamp_min(sum by (service_name) (rate(http_requests_total{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}[5m])), 0.001)
```

### Apdex (T = 0.25s)

`gauge` · percentunit

> (satisfied + tolerating/2) / total, with T=0.25s and 4T=1.0s. Both are exact histogram bucket boundaries, so no interpolation error.

**A** · `prometheus` · legend `apdex`

```promql
avg(svc:apdex:ratio5m{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"})
```

### Error Budget Remaining (30d)

`gauge` · percent

> Against a 99.5% availability SLO over 30 days. min() shows the worst-off service -- the one that will force a freeze first.

**A** · `prometheus` · legend `budget left`

```promql
100 * min(slo:error_budget_remaining:ratio30d{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"})
```

### Error Budget Burn Rate (1h window)

`timeseries` · short

> Burn rate 1× exhausts the budget exactly at 30 days. 14.4× is the standard multi-window fast-burn paging threshold (2% of a 30-day budget in 1 hour).

**A** · `prometheus` · legend `{{service_name}}`

```promql
slo:error_budget_burn_rate:ratio1h{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

**B** · `prometheus` · legend `sustainable (1×)`

```promql
vector(1)
```

**C** · `prometheus` · legend `fast-burn page threshold (14.4×)`

```promql
vector(14.4)
```

## SRE  ·  Payment Gateway & Dependency Health

> Maps to the wireframe's dependency / service-map panel. Decision supported: is the fault ours or the downstream gateway's?

### Payment Gateway P95 Latency by Method

`timeseries` · s

> Per-method P95 against the 2s SLO. The latency chaos scenario shows here first, 3-5s injected per payment.

**A** · `prometheus` · legend `p95 {{payment_method}}`

```promql
histogram_quantile(0.95, sum by (payment_method, le) (rate(payment_gateway_latency_seconds_bucket{environment="dev", payment_method=~".*"}[5m])))
```

### Payment Gateway Latency Distribution

`heatmap`

> Native histogram heatmap -- exposes bimodality that a P95 line hides. Two bands = two code paths or a partially degraded gateway pool.

**A** · `prometheus` · format=heatmap · legend `{{le}}`

```promql
sum by (le) (increase(payment_gateway_latency_seconds_bucket{environment="dev", payment_method=~".*"}[1m]))
```

### Payment Decline Reasons

`piechart` · short

> Business declines (insufficient_funds) versus technical failures (gateway_timeout) need completely different responses.

**A** · `prometheus` · legend `{{decline_reason}}`

```promql
sum by (decline_reason) (increase(payment_transactions_total{environment="dev", payment_method=~".*", status="declined"}[1h]))
```

### Payment Success Rate by Method

`bargauge` · percent

> One method collapsing while others hold is an instrument-specific gateway problem, not an outage.

**A** · `prometheus` · legend `{{payment_method}}`

```promql
100 * sum by (payment_method) (rate(payment_transactions_total{environment="dev", payment_method=~".*", status="success"}[5m])) / clamp_min(sum by (payment_method) (rate(payment_transactions_total{environment="dev", payment_method=~".*"}[5m])), 0.001)
```

### Dependency Health

`table`

> booking → payment edge health. downstream_dependency_up is set by the booking service from the outcome of its last outbound call, so it reflects the caller's real experience rather than a synthetic probe.

**A** · `prometheus` · instant · format=table

```promql
downstream_dependency_up{environment="dev"}
```

**B** · `prometheus` · instant · legend `booking p95 (incl. payment)`

```promql
histogram_quantile(0.95, sum by (le) (rate(booking_duration_seconds_bucket{environment="dev", route=~".*", payment_method=~".*"}[5m])))
```

**C** · `prometheus` · instant · legend `payment-attributed failures/s`

```promql
sum(rate(booking_failure_total{environment="dev", route=~".*", payment_method=~".*", reason=~"payment_.*"}[5m]))
```

**D** · `prometheus` · instant · legend `payments in flight`

```promql
sum(payment_requests_in_flight{environment="dev"})
```

### Payments In Flight (saturation)

`timeseries` · short

> USE: Saturation. Concurrency climbing while throughput is flat means requests are queueing -- the leading indicator of a latency incident.

**A** · `prometheus` · legend `{{gateway}}`

```promql
sum by (gateway) (payment_requests_in_flight{environment="dev"})
```

## SRE  ·  Runtime & Resource Saturation

> Sourced from the process_* / python_* metrics prometheus_client exposes automatically. No node_exporter or cAdvisor is deployed in this stack -- see the coverage note at the bottom of the dashboard.

### Resident Memory by Service

`bargauge` · bytes

> Red at 300MB matches the FlightSearchHighMemory alert threshold in alert_rules.yml, so the panel and the alert cannot drift apart.

**A** · `prometheus` · legend `{{service_name}}`

```promql
process_resident_memory_bytes{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

### Resident Memory Trend — memory-leak chaos detector

`timeseries` · bytes

> A monotonic staircase here is the leak. Query B overlays chaos state scaled to the axis, so an intentional experiment is visually distinguishable from a genuine regression.

**A** · `prometheus` · legend `{{service_name}}`

```promql
process_resident_memory_bytes{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

**B** · `prometheus` · legend `memory_leak chaos active`

```promql
sum by (scenario) (active_chaos_simulations{environment="dev", scenario="memory_leak"}) * 3e8
```

### CPU Utilisation by Service

`timeseries` · percent

> Percent of one CPU core. Values above 100 mean multiple cores are busy.

**A** · `prometheus` · legend `{{service_name}}`

```promql
100 * sum by (service_name) (rate(process_cpu_seconds_total{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}[5m]))
```

### Seats Available by Flight

`bargauge` · short

> Inventory saturation. Zero seats produces booking failures with reason=no_seats, which is expected business behaviour and must not be escalated as a reliability incident.

**A** · `prometheus` · legend `{{flight_id}} · {{route}}`

```promql
flight_seats_available{environment="dev", route=~".*"}
```

### Open File Descriptors

`timeseries` · short

> Descriptor exhaustion presents as connection errors that look like a network fault. Plotted against the actual rlimit.

**A** · `prometheus` · legend `{{service_name}}`

```promql
process_open_fds{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

**B** · `prometheus` · legend `limit {{service_name}}`

```promql
process_max_fds{environment="dev", service_name=~"flight-search-service|booking-service|payment-service"}
```

## SRE  ·  Logs, Traces & Error Analysis

> Loki and Jaeger. Decision supported: what exactly failed, and on which request?

### Log Volume by Level

`timeseries` · short

> Stacked log volume. A sudden ERROR band is often visible before a metric-based alert fires, because logs are not bucketed.

**A** · `loki` · legend `{{log_level}}`

```logql
sum by (log_level) (count_over_time(
  {environment="dev", service=~"flight-search-service|booking-service|payment-service"}
    | json | __error__="" | log_level=~"WARNING|ERROR" [1m]
))
```

### Top Error Sources

`table`

> Pareto of error messages -- the wireframe's 'recurring incident Pareto', built from logs. Caution: `message` is high-cardinality. If this panel gets slow, add `| pattern` to normalise messages into templates before grouping.

**A** · `loki`

```logql
topk(10, sum by (service_name, message) (count_over_time(
  {environment="dev", service=~"flight-search-service|booking-service|payment-service"}
    | json | __error__="" | log_level="ERROR" [1h]
)))
```

### Live Log Tail — full stream

`logs`

> Full structured stream for the current selection. Enable Live tailing from the panel menu for real-time follow. trace_id and span_id are extracted by | json and become clickable derived fields into Jaeger.

**A** · `loki`

```logql
{environment="dev", service=~"flight-search-service|booking-service|payment-service"}
  | json | __error__=""
  | log_level=~"WARNING|ERROR"
```

---

## Troubleshooting: symptom to cause

| Symptom | Most likely cause | Fix |
|---|---|---|
| Every panel says **Datasource not found** | Old `datasources.yml` still present alongside the new `datasources.yaml`, so provisioning aborted on a duplicate uid | `rm grafana/provisioning/datasources/datasources.yml` and restart Grafana. Check the container log for `datasource provisioning error` |
| `$service` dropdown is **empty** | `service_name` target label missing from `prometheus.yml` | Run preflight check 2. Reload Prometheus |
| Panels using `service_name` return **no data**, but the metric exists | An app is also exporting `service_name`, so Prometheus renamed it to `exported_service_name` | Remove the label from the app code. Topology belongs in target labels only |
| **Apdex** panel is empty or reads exactly 0 | The `le="0.25"` / `le="1.0"` exact matches do not match your bucket label formatting | Run preflight check 3 and edit `svc:apdex:ratio5m` to the literal strings you see |
| Business panels empty, technical panels fine | No booking traffic, or the load generator is not sending `payment_method` / `cabin_class` | `docker compose logs load-generator`. Confirm `booking_requests_total` has non-`other` label values |
| **Revenue at Risk** always 0 | No failed bookings yet — this is correct | `curl -XPOST localhost:8002/api/v1/chaos/error-spike/start` to prove the panel works, then stop it |
| All Loki panels empty | `environment` label missing from promtail, or promtail cannot read the docker socket | Run the Loki label checks above. `docker compose logs promtail` |
| Loki panels show **parse error** volume | `| json` hitting non-JSON lines from infrastructure containers | Already guarded by `| __error__=""`. If it persists, tighten the stream selector |
| Log lines show but `trace_id` is **not clickable** | Jaeger datasource uid changed, or the derived-field regex does not match | Check `derivedFields` in `datasources.yaml`. The regex needs exactly 32 hex chars, which also skips the `"0"` placeholder emitted outside a span |
| **Error Budget Remaining** is empty for ~an hour after startup | `increase(...[30d])` needs history to exist | Expected. It fills in as data accumulates |
| Latency panels look like a **sawtooth** | `$rate_window` too small for the selected time range | Widen `$rate_window` to `15m` or `1h` |
| `state-timeline` shows one solid grey band | The metric has no data, so every point is the `NO DATA` mapping | Check the underlying recording rule has evaluated |

---

## Chaos scenarios — proving the panels react

Each scenario sets `active_chaos_simulations{scenario="..."}` to 1, which drives the purple dashboard annotation and the **Active Chaos Simulations** stat. Always stop a scenario when finished: the `ChaosExperimentRunningTooLong` alert fires after 30 minutes because chaos left running silently corrupts every SLI on the dashboard.

```bash
# --- Memory leak: watch 'Resident Memory Trend' climb in a staircase ------
curl -XPOST localhost:8001/api/v1/chaos/memory-leak/start
#   Panels: Resident Memory by Service, Resident Memory Trend
#   Alert:  FlightSearchHighMemory at 300MB (~30 x 10MB blocks, about 1 min)
curl -XPOST localhost:8001/api/v1/chaos/memory-leak/stop

# --- Error spike: ~50% of bookings return 500 ---------------------------
curl -XPOST localhost:8002/api/v1/chaos/error-spike/start
#   Panels: Booking Success Rate, Revenue at Risk, Booking Outcome Mix
#           (reason=chaos_error_spike), Errors 5xx/sec, Error Budget Burn Rate
#   Alerts: BookingSuccessRateLow, ErrorBudgetFastBurn
curl -XPOST localhost:8002/api/v1/chaos/error-spike/stop

# --- Payment latency: 3-5s injected per payment -------------------------
curl -XPOST localhost:8003/api/v1/chaos/latency/start
#   Panels: Payment Gateway P95 by Method, Latency Distribution heatmap
#           (band shifts to the 3-5s rows), Payments In Flight, Apdex
#   Alerts: PaymentGatewayLatencyBreach, PaymentServiceHighLatency, ApdexDegraded
curl -XPOST localhost:8003/api/v1/chaos/latency/stop

# --- Verify nothing is left running ------------------------------------
curl -s localhost:9090/api/v1/query --data-urlencode \
  'query=sum by (scenario) (active_chaos_simulations)' | python3 -m json.tool
```

---

*61 PromQL and 5 LogQL queries across 40 panels in 7 rows.*
