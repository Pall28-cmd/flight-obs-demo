#!/usr/bin/env python3
"""
ServiceNow ITOM Extended Exporter
Exposes ITOM metrics as Prometheus metrics on /metrics endpoint
"""

from flask import Flask, Response
import sys
import os

# Add current dir to path
sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__)

# Import the ITOM generator
from servicenow_itom_extended import ServiceNowITOMExtended

# Initialize ITOM
itom = ServiceNowITOMExtended()

@app.route('/metrics', methods=['GET'])
def metrics():
    """Return Prometheus metrics"""
    metrics_output = itom.to_prometheus_metrics()
    
    # Add helper comments
    header = """# HELP servicenow_services_up Services currently up
# TYPE servicenow_services_up gauge
"""
    return Response(header + metrics_output, mimetype='text/plain')

@app.route('/api/itom/services-up', methods=['GET'])
def api_services_up():
    """JSON API for services up"""
    import json
    return Response(json.dumps(itom.get_services_up()), mimetype='application/json')

@app.route('/api/itom/major-incidents', methods=['GET'])
def api_major_incidents():
    """JSON API for incidents"""
    import json
    return Response(json.dumps(itom.get_major_incidents()), mimetype='application/json')

@app.route('/api/itom/critical-alerts', methods=['GET'])
def api_critical_alerts():
    """JSON API for alerts"""
    import json
    return Response(json.dumps(itom.get_critical_alerts()), mimetype='application/json')

@app.route('/api/itom/availability', methods=['GET'])
def api_availability():
    """JSON API for availability"""
    import json
    return Response(json.dumps(itom.get_availability()), mimetype='application/json')

@app.route('/api/itom/customers-impacted', methods=['GET'])
def api_customers_impacted():
    """JSON API for customer impact"""
    import json
    return Response(json.dumps(itom.get_customers_impacted()), mimetype='application/json')

@app.route('/api/itom/feeds-degraded', methods=['GET'])
def api_feeds_degraded():
    """JSON API for degraded feeds"""
    import json
    return Response(json.dumps(itom.get_feeds_degraded()), mimetype='application/json')

@app.route('/api/itom/service-rag', methods=['GET'])
def api_service_rag():
    """JSON API for service RAG status"""
    import json
    return Response(json.dumps(itom.get_service_availability_rag()), mimetype='application/json')

@app.route('/api/itom/active-incident', methods=['GET'])
def api_active_incident():
    """JSON API for active incident"""
    import json
    return Response(json.dumps(itom.get_active_major_incident()), mimetype='application/json')

@app.route('/api/itom/feed-health', methods=['GET'])
def api_feed_health():
    """JSON API for feed health"""
    import json
    return Response(json.dumps(itom.get_feed_health_table()), mimetype='application/json')

@app.route('/api/itom/critical-alerts-summary', methods=['GET'])
def api_critical_alerts_summary():
    """JSON API for critical alert summary"""
    import json
    return Response(json.dumps(itom.get_critical_alert_summary()), mimetype='application/json')

@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return Response('{"status": "ok"}', mimetype='application/json')

if __name__ == '__main__':
    print("🚀 ServiceNow ITOM Exporter starting...")
    print("📊 Metrics endpoint: http://localhost:9095/metrics")
    print("📋 APIs available at http://localhost:9095/api/itom/*")
    app.run(host='0.0.0.0', port=9095, debug=False)

