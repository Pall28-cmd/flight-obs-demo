/**
 * Minimal Express service showing metrics.js in use.
 * The instrumentation pattern to copy: normalise labels once at the top of the
 * handler, then record on every exit path including errors.
 *
 *   npm install express prom-client && node example-service.js
 */
'use strict';

const express = require('express');
const m = require('./metrics');

const SERVICE_NAME = process.env.SERVICE_NAME || 'booking-service-node';
const GATEWAY = process.env.PAYMENT_GATEWAY_NAME || 'razorpay-sim';

const app = express();
app.use(express.json());
app.use(m.metricsMiddleware(SERVICE_NAME));

m.initSeries({ scenarios: ['error_spike'], gateway: GATEWAY });

const chaos = { error_spike: false };

app.post('/api/v1/bookings', async (req, res) => {
  const route = m.normaliseRoute(req.body.origin, req.body.destination);
  const paymentMethod = m.normalisePaymentMethod(req.body.payment_method);
  const cabinClass = m.normaliseCabinClass(req.body.cabin_class);
  const amount = Number(req.body.amount) || 0;
  const start = process.hrtime.bigint();

  // Single exit point for every SPOG booking metric.
  const record = (statusCode, reason) => {
    const seconds = Number(process.hrtime.bigint() - start) / 1e9;
    m.bookingRequests.inc({
      route, payment_method: paymentMethod, cabin_class: cabinClass,
      status_code: String(statusCode),
    });
    m.bookingDuration.observe({ route, payment_method: paymentMethod }, seconds);
    if (!reason) {
      m.bookingSuccess.inc({ route, payment_method: paymentMethod, cabin_class: cabinClass });
      m.bookingValueInr.inc({ route, payment_method: paymentMethod }, amount);
    } else {
      const canonical = m.normaliseReason(reason);
      m.bookingFailure.inc({ route, payment_method: paymentMethod, reason: canonical });
      m.bookingValueAtRiskInr.inc(
        { route, payment_method: paymentMethod, reason: canonical }, amount,
      );
    }
  };

  try {
    if (chaos.error_spike && Math.random() < 0.5) {
      m.chaosInjections.inc({ scenario: 'error_spike' });
      record(500, 'chaos_error_spike');
      return res.status(500).json({ error: 'injected chaos error-spike' });
    }

    const paid = await callGateway(paymentMethod, amount);
    if (!paid.ok) {
      record(402, 'payment_declined');
      return res.status(402).json({ error: 'payment declined', reason: paid.reason });
    }

    record(201, null);
    return res.status(201).json({ booking_id: `BK${Date.now()}`, route, amount });
  } catch (err) {
    // Never let an unexpected throw skip the metric — that is how error rates
    // end up looking better than reality.
    record(500, 'unknown');
    return res.status(500).json({ error: 'internal error' });
  }
});

async function callGateway(paymentMethod, amount) {
  m.paymentRequestsInFlight.inc({ gateway: GATEWAY });
  const start = process.hrtime.bigint();
  try {
    await new Promise((r) => setTimeout(r, 50 + Math.random() * 150));
    const ok = Math.random() < 0.92;
    const seconds = Number(process.hrtime.bigint() - start) / 1e9;
    const status = ok ? 'success' : 'declined';
    const declineReason = ok
      ? 'none'
      : m.normaliseDeclineReason(
        ['gateway_declined', 'insufficient_funds', 'risk_rejected'][
          Math.floor(Math.random() * 3)
        ],
      );

    m.paymentGatewayLatency.observe(
      { payment_method: paymentMethod, gateway: GATEWAY, status }, seconds,
    );
    m.paymentTransactions.inc({
      payment_method: paymentMethod, gateway: GATEWAY, status,
      decline_reason: declineReason,
    });
    if (ok) m.paymentAmountInr.inc({ payment_method: paymentMethod, gateway: GATEWAY }, amount);

    return { ok, reason: declineReason };
  } finally {
    m.paymentRequestsInFlight.dec({ gateway: GATEWAY });
  }
}

app.post('/api/v1/chaos/error-spike/:action', (req, res) => {
  const on = req.params.action === 'start';
  chaos.error_spike = on;
  m.activeChaosSimulations.set({ scenario: 'error_spike' }, on ? 1 : 0);
  res.json({ status: `error-spike chaos ${on ? 'started' : 'stopped'}` });
});

app.get('/health', (_req, res) => res.json({ status: 'healthy', service: SERVICE_NAME }));
app.get('/metrics', m.metricsHandler());

const port = Number(process.env.PORT) || 8004;
app.listen(port, () => console.log(`${SERVICE_NAME} listening on ${port}`));
