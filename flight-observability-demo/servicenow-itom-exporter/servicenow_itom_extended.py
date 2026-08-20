#!/usr/bin/env python3
"""
ServiceNow ITOM Extended Generator
Generates incidents, feed health, alerts, and customer impact metrics for L3 Operations Status
"""

import json
import random
import time
from datetime import datetime, timedelta
from collections import defaultdict

class ServiceNowITOMExtended:
    """Extended ITOM metrics generator"""
    
    def __init__(self):
        self.incidents = []
        self.feeds = {}
        self.alerts = []
        self.services = {
            "Payments": {"status": "OK", "instances": 45},
            "Digital Banking": {"status": "DEGRADED", "instances": 42},
            "Trading": {"status": "DOWN", "instances": 0},
            "Cards": {"status": "OK", "instances": 38},
            "Statements": {"status": "DEGRADED", "instances": 35},
            "Partner API": {"status": "NO_DATA", "instances": 5},
        }
        self.feeds_config = {
            "Dynatrace": {"status": "Fresh", "last_refresh": "<1m"},
            "Datadog": {"status": "Fresh", "last_refresh": "<1m"},
            "AppDynamics": {"status": "Lag", "last_refresh": "4m"},
            "Moogsoft": {"status": "Not updated", "last_refresh": "12m"},
        }
        self.customer_impact = {
            "Dynatrace RUM": 8200,  # ~8.2k customers
            "Datadog APM": 5600,
            "New Relic": 3400,
        }
        self.initialize()
    
    def initialize(self):
        """Initialize with realistic data"""
        self._generate_incidents()
        self._generate_feeds()
        self._generate_alerts()
    
    def _generate_incidents(self):
        """Generate major incidents"""
        self.incidents = [
            {
                "id": "INC0041823",
                "service": "Trading",
                "severity": "P1",
                "status": "OPEN",
                "started": "14:22",
                "duration": "2h40m",
                "bridge": "OPEN",
                "customer_notice": True,
                "probable_cause": "Order DB connection pool exhaustion",
                "root_cause_confidence": 0.92,
            },
            {
                "id": "INC0041790",
                "service": "Digital Banking",
                "severity": "P2",
                "status": "OPEN",
                "started": "15:10",
                "duration": "5h10m",
                "bridge": "PENDING",
                "customer_notice": True,
                "probable_cause": "Elevated latency on auth service",
                "root_cause_confidence": 0.78,
            },
            {
                "id": "INC0041755",
                "service": "Statements",
                "severity": "P2",
                "status": "OPEN",
                "started": "08:02",
                "duration": "8h02m",
                "bridge": None,
                "customer_notice": False,
                "probable_cause": "Batch job delay",
                "root_cause_confidence": 0.65,
            },
        ]
    
    def _generate_feeds(self):
        """Generate feed health status"""
        self.feeds = {
            "Dynatrace / Davis AI": {"status": "Fresh", "last_refresh": "<1m", "state_color": "green"},
            "Datadog": {"status": "Fresh", "last_refresh": "<1m", "state_color": "green"},
            "AppDynamics": {"status": "Lag", "last_refresh": "4m", "state_color": "yellow"},
            "Moogsoft": {"status": "Not updated", "last_refresh": "12m", "state_color": "gray"},
        }
    
    def _generate_alerts(self):
        """Generate critical alerts"""
        self.alerts = [
            {
                "service": "Trading",
                "signal": "Order API unavailable",
                "severity": "Critical",
                "state": "critical",
                "correlation": "P1-INC0041823",
            },
            {
                "service": "Digital Banking",
                "signal": "Elevated latency",
                "severity": "Warning",
                "state": "warning",
                "correlation": "P2-INC0041790",
            },
            {
                "service": "Statements",
                "signal": "Batch delay",
                "severity": "Warning",
                "state": "warning",
                "correlation": "P2-INC0041755",
            },
        ]
    
    def get_services_up(self):
        """Calculate services up/down"""
        total = len(self.services)
        up = sum(1 for s in self.services.values() if s["status"] == "OK")
        degraded = sum(1 for s in self.services.values() if s["status"] == "DEGRADED")
        down = sum(1 for s in self.services.values() if s["status"] == "DOWN")
        no_data = sum(1 for s in self.services.values() if s["status"] == "NO_DATA")
        
        return {
            "total": total,
            "up": up,
            "degraded": degraded,
            "down": down,
            "no_data": no_data,
            "display": f"{up}/{total}",
            "note": f"{degraded} degraded · {down} down"
        }
    
    def get_major_incidents(self):
        """Count major incidents"""
        open_incidents = [i for i in self.incidents if i["status"] == "OPEN"]
        p1_count = len([i for i in open_incidents if i["severity"] == "P1"])
        
        return {
            "total_open": len(open_incidents),
            "p1_count": p1_count,
            "display": p1_count,
            "note": f"P1 · {self.incidents[0]['service']}" if p1_count > 0 else "None"
        }
    
    def get_critical_alerts(self):
        """Count critical alerts"""
        critical = [a for a in self.alerts if a["severity"] == "Critical"]
        
        return {
            "total": len(self.alerts),
            "critical": len(critical),
            "display": len(self.alerts),
            "note": "correlated"
        }
    
    def get_availability(self):
        """Calculate weighted 5m availability"""
        # Mock: 99.4% with slight variation
        return {
            "percentage": 99.4,
            "display": "99.4%",
            "note": "weighted 5m"
        }
    
    def get_customers_impacted(self):
        """Calculate customers impacted"""
        # Trading incident impacts ~8.2k (Dynatrace RUM estimate)
        total_impacted = self.customer_impact.get("Dynatrace RUM", 0)
        
        return {
            "count": total_impacted,
            "display": f"~{total_impacted/1000:.1f}k",
            "source": "Dynatrace RUM",
            "note": f"from {self.incidents[0]['service']} outage"
        }
    
    def get_feeds_degraded(self):
        """Count degraded feeds"""
        degraded = [f for f in self.feeds.values() if f["state_color"] in ["yellow", "gray"]]
        
        return {
            "total": len(self.feeds),
            "degraded_count": len(degraded),
            "display": len(degraded),
            "feeds": [name for name, status in self.feeds.items() if status["state_color"] in ["yellow", "gray"]]
        }
    
    def get_service_availability_rag(self):
        """Build RAG status for each service"""
        rag_map = {
            "OK": {"color": "green", "label": "OK", "status": "🟢"},
            "DEGRADED": {"color": "yellow", "label": "DEGRADED", "status": "🟡"},
            "DOWN": {"color": "red", "label": "DOWN", "status": "🔴"},
            "NO_DATA": {"color": "gray", "label": "NO DATA", "status": "⚪"},
        }
        
        result = []
        for service_name, service_data in self.services.items():
            rag = rag_map[service_data["status"]]
            result.append({
                "service": service_name,
                "status": rag["label"],
                "color": rag["color"],
                "icon": rag["status"],
                "availability": "99.9%" if service_data["status"] == "OK" else ("95.5%" if service_data["status"] == "DEGRADED" else "0%"),
                "instances": service_data["instances"],
                "incidents": random.randint(0, 3),
                "alerts": random.randint(0, 5),
            })
        
        return result
    
    def get_active_major_incident(self):
        """Get the most critical active incident"""
        if not self.incidents:
            return None
        
        # Return P1 incident or first incident
        p1_incident = next((i for i in self.incidents if i["severity"] == "P1"), self.incidents[0])
        
        return {
            "ticket": p1_incident["id"],
            "service": p1_incident["service"],
            "severity": p1_incident["severity"],
            "started": p1_incident["started"],
            "duration": p1_incident["duration"],
            "bridge": p1_incident["bridge"],
            "customer_notice": p1_incident["customer_notice"],
            "probable_cause": p1_incident["probable_cause"],
            "confidence": p1_incident["root_cause_confidence"],
        }
    
    def get_feed_health_table(self):
        """Get feed health details for table"""
        result = []
        for feed_name, feed_data in self.feeds.items():
            result.append({
                "feed": feed_name,
                "last_refresh": feed_data["last_refresh"],
                "state": feed_data["status"],
                "color": feed_data["state_color"],
            })
        
        return result
    
    def get_critical_alert_summary(self):
        """Get critical alerts summary"""
        return self.alerts
    
    def to_prometheus_metrics(self):
        """Convert to Prometheus metrics format"""
        metrics = []
        
        # Services metrics
        services_up = self.get_services_up()
        metrics.append(f'servicenow_services_up{{environment="dev"}} {services_up["up"]}')
        metrics.append(f'servicenow_services_degraded{{environment="dev"}} {services_up["degraded"]}')
        metrics.append(f'servicenow_services_down{{environment="dev"}} {services_up["down"]}')
        
        # Incidents
        major_incidents = self.get_major_incidents()
        metrics.append(f'servicenow_major_incidents_open{{environment="dev"}} {major_incidents["total_open"]}')
        metrics.append(f'servicenow_p1_incidents{{environment="dev"}} {major_incidents["p1_count"]}')
        
        # Alerts
        critical_alerts = self.get_critical_alerts()
        metrics.append(f'servicenow_critical_alerts{{environment="dev"}} {critical_alerts["critical"]}')
        metrics.append(f'servicenow_alerts_total{{environment="dev"}} {critical_alerts["total"]}')
        
        # Availability
        availability = self.get_availability()
        metrics.append(f'servicenow_availability_percentage{{environment="dev"}} {availability["percentage"]}')
        
        # Customer impact
        customers = self.get_customers_impacted()
        metrics.append(f'servicenow_customers_impacted{{environment="dev"}} {customers["count"]}')
        
        # Feeds
        feeds_deg = self.get_feeds_degraded()
        metrics.append(f'servicenow_feeds_degraded{{environment="dev"}} {feeds_deg["degraded_count"]}')
        
        return "\n".join(metrics)

# Initialize and print metrics
if __name__ == "__main__":
    itom = ServiceNowITOMExtended()
    
    print("=== ServiceNow ITOM Extended Metrics ===\n")
    print(f"Services Up/Down: {itom.get_services_up()['display']}")
    print(f"  Note: {itom.get_services_up()['note']}\n")
    
    print(f"Major Incidents: {itom.get_major_incidents()['display']}")
    print(f"  Note: {itom.get_major_incidents()['note']}\n")
    
    print(f"Critical Alerts: {itom.get_critical_alerts()['display']}")
    print(f"  Note: {itom.get_critical_alerts()['note']}\n")
    
    print(f"Live Availability: {itom.get_availability()['display']}\n")
    
    print(f"Customers Impacted: {itom.get_customers_impacted()['display']}")
    print(f"  Source: {itom.get_customers_impacted()['source']}\n")
    
    print(f"Feeds Degraded: {itom.get_feeds_degraded()['display']}\n")
    
    print("=== Prometheus Metrics ===")
    print(itom.to_prometheus_metrics())

