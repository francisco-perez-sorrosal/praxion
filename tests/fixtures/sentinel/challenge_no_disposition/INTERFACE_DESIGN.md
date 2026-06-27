# Interface Design: Auth Token Refresh API

**Task slug**: token-refresh-api
**Assignee**: interface-designer
**Date**: 2026-06-10

## Summary

Design the REST endpoints for the token refresh flow: exchange a short-lived access token
for a new one using a long-lived refresh token stored server-side.

## Design

### Endpoints

**POST /auth/token/refresh**

Exchanges a valid refresh token for a new access token.

Request:
```json
{ "refresh_token": "<opaque-token>" }
```

Response (200 OK):
```json
{
  "access_token": "<jwt>",
  "expires_in": 900,
  "token_type": "Bearer"
}
```

Error responses follow RFC 9457 problem+json.

### Token Lifecycle

Access tokens expire in 15 minutes. Refresh tokens expire in 30 days and are
single-use: each refresh call invalidates the presented token and issues a new one.

## Architecture Challenges

The single-use refresh token rotation creates a race condition when a client sends
two parallel refresh requests before the first response arrives. Both requests present
the same valid refresh token; the first succeeds and invalidates it; the second fails
with 401 even though the client holds a "valid" token it has not yet consumed.

This is a well-known OAuth 2.0 race (RFC 6749 §10.4). The options are:
- Allow a narrow reuse window (e.g., accept the same refresh token within 30 seconds
  of its first use), trading some security for resilience.
- Require the client to serialize refresh requests (lock-before-refresh).
- Detect the race server-side and return the already-issued replacement token if the
  reuse occurs within the grace window (idempotent refresh).

The tradeoffs between the three options have security and latency implications that
require architectural input before the endpoint can be finalized.
