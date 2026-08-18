# Node.js reference instrumentation

The three services in this repo are Python/FastAPI. These files are the exact
Node.js equivalent, for when you add a Node service and need it to feed the same
Grafana dashboard without editing any panel.

| File | Purpose |
|---|---|
| `metrics.js` | Metric registry, label normalisers, Express middleware and `/metrics` handler |
| `example-service.js` | Minimal Express booking service showing the instrumentation pattern |

```bash
npm init -y && npm install express prom-client
node example-service.js
curl -s localhost:8004/metrics | grep booking_
```

## Three things that must match the Python services exactly

1. **Metric and label names.** `booking_success_total{route,payment_method,cabin_class}`
   in Node must be identical in Python. The dashboard sums across services.

2. **Histogram bucket boundaries.** Prometheus cannot merge histograms with
   different buckets — `histogram_quantile()` over a sum of mismatched buckets
   returns a plausible-looking wrong number. `0.25` and `1.0` in
   `http_request_duration_seconds` are the Apdex T and 4T boundaries that
   `svc:apdex:ratio5m` matches on by exact `le` label.

3. **No `service_name` or `environment` label.** Those are Prometheus target
   labels. Add the new service to `prometheus.yml` with its own
   `service_name` / `environment` target labels instead:

   ```yaml
     - job_name: "booking-service-node"
       static_configs:
         - targets: ["booking-service-node:8004"]
           labels:
             service_name: booking-service-node
             environment: dev
             tier: application
             business_service: booking
   ```

## Also required for full dashboard coverage

- `client.collectDefaultMetrics()` — supplies `process_cpu_seconds_total`,
  `process_resident_memory_bytes`, `process_open_fds`, `process_max_fds`, which
  the "Runtime & Resource Saturation" row reads.
- **Structured JSON logs on stdout** with `timestamp`, `log_level`,
  `service_name`, `message`, `trace_id`, `span_id` — the Loki panels do
  `| json` and then filter on `log_level`. Use `pino` and let promtail's
  docker_sd pick the container up automatically. Without `trace_id` in the line,
  the log-to-trace derived field in `datasources.yaml` has nothing to match.
- **OpenTelemetry**: `@opentelemetry/sdk-node` with
  `@opentelemetry/exporter-trace-otlp-http` pointed at
  `http://otel-collector:4318/v1/traces`.
