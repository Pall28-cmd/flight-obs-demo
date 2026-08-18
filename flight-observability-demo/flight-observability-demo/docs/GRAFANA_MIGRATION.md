# Power BI SPOG → Grafana migration

Migration of the Power BI Single Pane of Glass wireframe onto the live
Prometheus / Loki / Jaeger stack.

Dashboard: **Flight Booking — Digital Operations Command Center (SPOG)**
`uid: flight-booking-spog`

---

## 1. Deploy

```bash
# ⚠ Do this first. Grafana reads every .yml AND .yaml file in a provisioning
# directory. The repo previously shipped .yml versions of both files; leaving
# them alongside the new .yaml files makes provisioning abort on a duplicate
# uid and Grafana starts with NO datasources.
rm -f grafana/provisioning/datasources/datasources.yml
rm -f grafana/provisioning/dashboards/dashboards.yml

# Rebuild the three services -- the Dockerfiles now copy metrics.py as well as
# app.py, so a plain `up` without --build will run the old images.
docker compose up -d --build

# Confirm Prometheus loaded both rule files
curl -s localhost:9090/api/v1/rules | python3 -m json.tool | grep '"name"'

# Confirm Grafana provisioned cleanly (should print nothing)
docker compose logs grafana 2>&1 | grep -i "provisioning error"
```

Open <http://localhost:3000/d/flight-booking-spog>. Allow 2–3 minutes for the
recording rules to produce their first samples; **Error Budget Remaining** uses
a 30-day window and stays empty longest.

---

## 2. What changed

### Application code

| File | Change |
|---|---|
| `services/*/metrics.py` | **New.** Metric registry, bounded label vocabularies, normalisers |
| `services/flight-search/app.py` | `flight_search_requests_total`, duration, zero-results, chaos gauge |
| `services/booking/app.py` | `create_booking` rewritten around a single `_record()` exit point covering all six outcome paths |
| `services/payment/app.py` | `process_payment` rewritten: gateway latency histogram, transaction counter with decline reasons, in-flight gauge |
| `services/*/Dockerfile` | `COPY app.py metrics.py ./` |
| `load-generator/generate_traffic.py` | Sends `cabin_class` and `payment_method`; weighted route distribution |
| `nodejs-reference/` | **New.** Node/Express equivalent of `metrics.py` |

All pre-existing metrics were left in place. `alert_rules.yml` and the original
`observability-dashboard.json` still work unchanged.

### Infrastructure

| File | Change |
|---|---|
| `prometheus/prometheus.yml` | `service_name`, `environment`, `tier`, `business_service` **target labels**; loads `recording_rules.yml` |
| `prometheus/recording_rules.yml` | **New.** 19 rules |
| `prometheus/alert_rules.yml` | 8 new alerts consuming those rules |
| `promtail/promtail-config.yml` | Constant `environment` label so LogQL can filter like PromQL |
| `docker-compose.yml` | Mounts `recording_rules.yml`; enables `--web.enable-lifecycle` |
| `grafana/provisioning/datasources/datasources.yaml` | **New.** Loki→Jaeger derived fields, Jaeger→Loki correlation, exemplars |
| `grafana/provisioning/dashboards/dashboards.yaml` | **New.** Provider for the `Flight Booking` folder |

---

## 3. The one design decision worth knowing

You asked for `service_name` as a metric label. It is instead applied as a
**Prometheus target label** in `prometheus.yml`, and this is deliberate.

Prometheus target labels take precedence over labels exported by the
application. If a service exported `service_name` on a metric *and* the scrape
config set it as a target label, Prometheus would rename the app's copy to
`exported_service_name`. Every `service_name=~"$service"` selector in the
dashboard would then match nothing — and it would fail silently, showing empty
panels rather than an error.

Applying it once at scrape time also means it lands on metrics the app does not
control, including the `process_*` and `python_*` families that
`prometheus_client` registers automatically. The "Runtime & Resource Saturation"
row depends on that.

So the split is: **topology labels** (`service_name`, `environment`, `tier`,
`business_service`) come from the scrape config; **measurement labels**
(`route`, `payment_method`, `status_code`, `cabin_class`, `decline_reason`)
come from the code. If you would rather set `service_name` in-app, remove it
from `prometheus.yml` at the same time — the two must not both define it.

---

## 4. Cardinality

Every label value is whitelisted in `metrics.py` before use. `normalise_route()`
collapses anything unrecognised to `other`, so a malformed or hostile
`?origin=` parameter cannot create a new series.

| Metric | Worst-case series |
|---|---|
| `booking_requests_total` | 720 |
| `booking_failure_total` | 252 |
| `payment_gateway_latency_seconds_bucket` | 132 |
| `booking_success_total` | 144 |
| **Total added** | **≈1,500** |

Negligible for a single Prometheus. The rule to keep: **never put an
unnormalised string in a label.** The one place this discipline is deliberately
relaxed is the "Top Error Sources" Loki panel, which groups by `message`. That
runs at query time against Loki, not as stored Prometheus series, but it will
slow down as volume grows — add `| pattern` to template the messages when it
does.

---

## 5. Persona mapping

The wireframe's Power BI pages become Grafana rows, keeping the persona
separation.

| Wireframe page | Grafana row | Source |
|---|---|---|
| L1 Executive & Governance | Leadership · Executive Summary | Recording rules, 5m |
| L1 business impact | Leadership · Business Service Health & Impact | `booking_*`, `payment_*` |
| L3 Operations Status | Leadership · Live Operations Status | `up`, chaos gauges, Loki |
| S1 Operations & Observability | SRE · Golden Signals | Raw PromQL, `$rate_window` |
| S1 dependency health | SRE · Payment Gateway & Dependency Health | Gateway histograms |
| S1 infrastructure | SRE · Runtime & Resource Saturation | `process_*` |
| S1 logs & traces | SRE · Logs, Traces & Error Analysis | Loki + Jaeger |
| L2 Maturity Scorecard | **not migrated** | See below |

Leadership rows read fixed-5m recording rules on purpose, so an executive KPI
does not move because an SRE changed `$rate_window`. SRE rows use raw PromQL
with `$rate_window` because varying the smoothing window is exactly what you
want while debugging.

---

## 6. What was deliberately not migrated

The wireframe assumed ServiceNow ITSM/ITOM, a CMDB, Moogsoft and a manually
scored CACI maturity workbook. Those panels have **no source** in this stack.
They were left out rather than populated with numbers that would look
authoritative and be fiction:

- MTTR / MTTA / MTTD by line of business
- SLA compliance % and breach-by-support-group
- Monitoring coverage % (needs a CMDB inventory to divide by)
- Automated / machine-assisted resolution %
- Neuro maturity scorecard across five dimensions
- Governance and audit findings
- Incident / change / CI correlation

Every one is an *organisational* measure — how fast humans respond, how much of
the estate is instrumented, how mature the practice is. Grafana measures the
*system*. The Leadership rows answer the same executive questions from live
signals instead: **Availability** and **Apdex** in place of SLA compliance,
**Revenue at Risk ₹/hr** in place of business-impact ratings, **Error Budget
Remaining** in place of a maturity score.

Recommendation: keep Power BI as the system of record for ServiceNow-derived and
manually scored KPIs on a daily-to-monthly cadence, and use Grafana for
everything real-time. Cross-link them. The full table with the reasoning is in
the **Trace Navigation & Wireframe Coverage Notes** panel at the bottom of the
dashboard, so it is visible to anyone who opens it — including Manish.

If MTTR in Grafana is genuinely wanted, the smallest credible path is a
ServiceNow → Prometheus exporter, or Grafana's Infinity datasource against the
ServiceNow Table API. Scope that as separate work; there is no honest way to
derive it from Prometheus.

The `business_service` and `tier` target labels in `prometheus.yml` are the hook
for LOB slicing once a CMDB mapping exists.

---

## 7. Before showing this to anyone

- [ ] **Agree the IT Health Score weights.** `spog:it_health_score` is
      40% availability / 30% Apdex / 30% booking success. Those weights are a
      starting point, not a standard. A single composite invites "why is it 78?"
      and the weighting has to be able to answer.
- [ ] **Confirm the SLO.** 99.5% availability over 30 days is hard-coded as the
      `0.005` divisor in two recording rules. Change both together.
- [ ] **Set the Revenue at Risk thresholds.** Amber ₹20k/hr and red ₹60k/hr are
      placeholders.
- [ ] **Run preflight check 3** in the PromQL guide. If the `le` label is not
      formatted as `"0.25"` / `"1.0"`, the Apdex rule needs editing.
- [ ] **Point out the coverage-notes panel.** Leadership will look for SLA and
      MTTR because the wireframe had them.
- [ ] **Stop all chaos scenarios.** Chaos left running corrupts every SLI.

---

## 8. Files

```
docs/PROMQL_VERIFICATION_GUIDE.md      61 PromQL + 5 LogQL queries, preflight
                                       checks, troubleshooting, chaos runbook
docs/GRAFANA_MIGRATION.md              this file
grafana/provisioning/dashboards/json/
  flight_booking_grafana_dashboard.json 48 panels, 7 rows, 6 variables
grafana/provisioning/dashboards/dashboards.yaml
grafana/provisioning/datasources/datasources.yaml
prometheus/prometheus.yml              target labels
prometheus/recording_rules.yml         19 rules
prometheus/alert_rules.yml             11 alerts (3 original + 8 new)
promtail/promtail-config.yml           environment label
services/{flight-search,booking,payment}/metrics.py
services/{flight-search,booking,payment}/app.py
nodejs-reference/{metrics.js,example-service.js,README.md}
```
