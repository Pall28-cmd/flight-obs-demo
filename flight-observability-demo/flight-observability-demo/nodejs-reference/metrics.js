/**
 * SPOG metric registry — Node.js / Express reference implementation.
 *
 * The three services in this repo are Python/FastAPI. This module is the exact
 * equivalent for any Node service you add, so the same Grafana dashboard works
 * without changing a single panel query.
 *
 *   npm install prom-client express
 *
 * The labelling contract is identical to services/<svc>/metrics.py:
 *
 *   1. `service_name` and `environment` are NOT set here. They are Prometheus
 *      target labels from prometheus.yml. If you set them on a metric,
 *      Prometheus renames yours to `exported_service_name` and every
 *      `service_name=~"$service"` selector in the dashboard silently matches
 *      nothing.
 *   2. Histogram buckets must match the Python services exactly, or
 *      histogram_quantile() over a sum of both services' buckets is wrong.
 *      Prometheus cannot combine histograms with different bucket boundaries.
 *   3. Every label value goes through a normaliser first. An un-normalised
 *      label is an unbounded cardinality bug waiting to page you.
 */

'use strict';

const client = require('prom-client');

const registry = new client.Registry();

// Adds process_cpu_seconds_total, process_resident_memory_bytes,
// process_open_fds, process_max_fds and the nodejs_* family. The dashboard's
// "Runtime & Resource Saturation" row reads the process_* metrics, so this line
// is required, not optional.
client.collectDefaultMetrics({ register: registry });

// ---------------------------------------------------------------------------
// Bounded label vocabularies
// ---------------------------------------------------------------------------
const KNOWN_ROUTES = new Set([
  'DEL-BOM', 'DEL-BLR', 'DEL-GOI', 'BOM-DEL', 'BLR-HYD',
]);
const KNOWN_AIRPORTS = new Set(['DEL', 'BOM', 'BLR', 'HYD', 'GOI', 'ANY']);
const KNOWN_CABIN_CLASSES = new Set(['economy', 'premium_economy', 'business']);
const KNOWN_PAYMENT_METHODS = new Set([
  'credit_card', 'debit_card', 'upi', 'netbanking', 'wallet',
]);
const FAILURE_REASONS = new Set([
  'no_seats', 'payment_declined', 'payment_unreachable', 'payment_timeout',
  'invalid_request', 'chaos_error_spike', 'unknown',
]);
const DECLINE_REASONS = new Set([
  'none', 'gateway_declined', 'insufficient_funds', 'risk_rejected',
  'gateway_timeout', 'invalid_instrument',
]);

function normaliseRoute(origin, destination) {
  const o = String(origin || 'ANY').toUpperCase().slice(0, 3);
  const d = String(destination || 'ANY').toUpperCase().slice(0, 3);
  const route = `${o}-${d}`;
  if (KNOWN_ROUTES.has(route)) return route;
  if (o === 'ANY' || d === 'ANY') {
    return KNOWN_AIRPORTS.has(o) ? route : 'other';
  }
  return 'other';
}

function normaliseCabinClass(cc) {
  const v = String(cc || 'economy').toLowerCase();
  return KNOWN_CABIN_CLASSES.has(v) ? v : 'other';
}

function normalisePaymentMethod(pm) {
  const v = String(pm || 'credit_card').toLowerCase().replace(/[-\s]/g, '_');
  return KNOWN_PAYMENT_METHODS.has(v) ? v : 'other';
}

function normaliseReason(r) {
  const v = String(r || 'unknown').toLowerCase();
  return FAILURE_REASONS.has(v) ? v : 'unknown';
}

function normaliseDeclineReason(r) {
  const v = String(r || 'none').toLowerCase();
  return DECLINE_REASONS.has(v) ? v : 'gateway_declined';
}

// ---------------------------------------------------------------------------
// Baseline RED metrics. Names, label names AND bucket boundaries must match the
// Python services exactly — the dashboard sums buckets across all services.
// ---------------------------------------------------------------------------
const httpRequestsTotal = new client.Counter({
  name: 'http_requests_total',
  help: 'Total HTTP requests',
  labelNames: ['service', 'method', 'endpoint', 'status'],
  registers: [registry],
});

const httpRequestDuration = new client.Histogram({
  name: 'http_request_duration_seconds',
  help: 'Request latency (seconds)',
  labelNames: ['service', 'endpoint'],
  // prometheus_client's Python defaults. Do not "tidy" these: 0.25 and 1.0 are
  // the Apdex T and 4T boundaries the svc:apdex:ratio5m recording rule reads by
  // exact le label match.
  buckets: [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0,
    2.5, 5.0, 7.5, 10.0],
  registers: [registry],
});

// ---------------------------------------------------------------------------
// Flight search
// ---------------------------------------------------------------------------
const flightSearchRequests = new client.Counter({
  name: 'flight_search_requests_total',
  help: 'Flight search requests, dimensioned by route, cabin class and HTTP status.',
  labelNames: ['route', 'cabin_class', 'status_code'],
  registers: [registry],
});

const flightSearchDuration = new client.Histogram({
  name: 'flight_search_duration_seconds',
  help: 'End-to-end flight search handler duration in seconds.',
  labelNames: ['route', 'cabin_class'],
  buckets: [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
  registers: [registry],
});

const flightSearchZeroResults = new client.Counter({
  name: 'flight_search_zero_results_total',
  help: 'Searches that returned no flights.',
  labelNames: ['route', 'cabin_class'],
  registers: [registry],
});

// ---------------------------------------------------------------------------
// Booking funnel
// ---------------------------------------------------------------------------
const bookingRequests = new client.Counter({
  name: 'booking_requests_total',
  help: 'All booking attempts received, whatever the outcome.',
  labelNames: ['route', 'payment_method', 'cabin_class', 'status_code'],
  registers: [registry],
});

const bookingSuccess = new client.Counter({
  name: 'booking_success_total',
  help: 'Bookings confirmed end to end.',
  labelNames: ['route', 'payment_method', 'cabin_class'],
  registers: [registry],
});

const bookingFailure = new client.Counter({
  name: 'booking_failure_total',
  help: 'Bookings that did not confirm, by canonical failure reason.',
  labelNames: ['route', 'payment_method', 'reason'],
  registers: [registry],
});

const bookingDuration = new client.Histogram({
  name: 'booking_duration_seconds',
  help: 'End-to-end booking duration including the downstream payment call.',
  labelNames: ['route', 'payment_method'],
  buckets: [0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0],
  registers: [registry],
});

const bookingValueInr = new client.Counter({
  name: 'booking_value_inr_total',
  help: 'Cumulative confirmed booking value in INR.',
  labelNames: ['route', 'payment_method'],
  registers: [registry],
});

const bookingValueAtRiskInr = new client.Counter({
  name: 'booking_value_at_risk_inr_total',
  help: 'Cumulative INR value of booking attempts that failed.',
  labelNames: ['route', 'payment_method', 'reason'],
  registers: [registry],
});

const flightSeatsAvailable = new client.Gauge({
  name: 'flight_seats_available',
  help: 'Seats currently available per flight.',
  labelNames: ['flight_id', 'route'],
  registers: [registry],
});

// ---------------------------------------------------------------------------
// Payment gateway
// ---------------------------------------------------------------------------
const paymentGatewayLatency = new client.Histogram({
  name: 'payment_gateway_latency_seconds',
  help: 'Latency of the outbound payment gateway call in seconds.',
  labelNames: ['payment_method', 'gateway', 'status'],
  // 0.5 and 2.0 are exact boundaries so the SLO panels need no interpolation.
  buckets: [0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 10.0],
  registers: [registry],
});

const paymentTransactions = new client.Counter({
  name: 'payment_transactions_total',
  help: 'Payment transactions attempted. decline_reason=none on the success path.',
  labelNames: ['payment_method', 'gateway', 'status', 'decline_reason'],
  registers: [registry],
});

const paymentAmountInr = new client.Counter({
  name: 'payment_amount_inr_total',
  help: 'Cumulative INR value of captured payments.',
  labelNames: ['payment_method', 'gateway'],
  registers: [registry],
});

const paymentRequestsInFlight = new client.Gauge({
  name: 'payment_requests_in_flight',
  help: 'Payment requests currently being processed.',
  labelNames: ['gateway'],
  registers: [registry],
});

const paymentGatewayUp = new client.Gauge({
  name: 'payment_gateway_up',
  help: '1 if the payment gateway is reachable, else 0.',
  labelNames: ['gateway'],
  registers: [registry],
});

// ---------------------------------------------------------------------------
// Chaos state
// ---------------------------------------------------------------------------
const activeChaosSimulations = new client.Gauge({
  name: 'active_chaos_simulations',
  help: '1 while a chaos scenario is active in this service, else 0.',
  labelNames: ['scenario'],
  registers: [registry],
});

const chaosInjections = new client.Counter({
  name: 'chaos_injections_total',
  help: 'Count of individual chaos fault injections applied.',
  labelNames: ['scenario'],
  registers: [registry],
});

/** Pre-create gauge children so panels render before the first real event. */
function initSeries({ scenarios = [], gateway = null } = {}) {
  scenarios.forEach((scenario) => activeChaosSimulations.set({ scenario }, 0));
  if (gateway) {
    paymentGatewayUp.set({ gateway }, 1);
    paymentRequestsInFlight.set({ gateway }, 0);
  }
}

// ---------------------------------------------------------------------------
// Express wiring
// ---------------------------------------------------------------------------

/**
 * RED middleware. `endpoint` uses the matched route pattern (req.route.path),
 * not req.path — otherwise every /api/v1/bookings/BK1234 becomes its own label
 * value and the metric explodes.
 */
function metricsMiddleware(serviceName) {
  return (req, res, next) => {
    const start = process.hrtime.bigint();
    res.on('finish', () => {
      const seconds = Number(process.hrtime.bigint() - start) / 1e9;
      const endpoint = (req.route && req.route.path)
        || (req.baseUrl ? `${req.baseUrl}(unmatched)` : 'unmatched');
      httpRequestsTotal.inc({
        service: serviceName,
        method: req.method,
        endpoint,
        status: String(res.statusCode),
      });
      httpRequestDuration.observe({ service: serviceName, endpoint }, seconds);
    });
    next();
  };
}

/** GET /metrics handler. */
function metricsHandler() {
  return async (_req, res) => {
    res.set('Content-Type', registry.contentType);
    res.end(await registry.metrics());
  };
}

module.exports = {
  registry,
  metricsMiddleware,
  metricsHandler,
  initSeries,
  // normalisers
  normaliseRoute,
  normaliseCabinClass,
  normalisePaymentMethod,
  normaliseReason,
  normaliseDeclineReason,
  // metrics
  httpRequestsTotal,
  httpRequestDuration,
  flightSearchRequests,
  flightSearchDuration,
  flightSearchZeroResults,
  bookingRequests,
  bookingSuccess,
  bookingFailure,
  bookingDuration,
  bookingValueInr,
  bookingValueAtRiskInr,
  flightSeatsAvailable,
  paymentGatewayLatency,
  paymentTransactions,
  paymentAmountInr,
  paymentRequestsInFlight,
  paymentGatewayUp,
  activeChaosSimulations,
  chaosInjections,
};
