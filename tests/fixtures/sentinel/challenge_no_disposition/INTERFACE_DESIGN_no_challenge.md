# Interface Design: Health Check Endpoint

**Task slug**: health-check
**Assignee**: interface-designer
**Date**: 2026-06-15

## Summary

A minimal health check endpoint for load balancer probes and uptime monitors.

## Design

### Endpoint

**GET /health**

Returns the service liveness status. No authentication required.

Response (200 OK):
```json
{ "status": "ok", "version": "1.2.3" }
```

Response (503 Service Unavailable) when a critical dependency is unreachable:
```json
{ "status": "degraded", "reason": "database unreachable" }
```

### Notes

- Kept deliberately simple: no deep dependency checks (those go on `/health/ready`).
- The endpoint must respond within 100 ms to avoid false-positive load balancer evictions.
- No caching — each call probes the live service state.
