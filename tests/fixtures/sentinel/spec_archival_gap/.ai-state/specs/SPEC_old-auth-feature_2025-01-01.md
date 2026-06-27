# SPEC: old-auth-feature (archived 2025-01-01)

## Goal

Behavioral specification for old-auth-feature, archived 2025-01-01.

## Behavioral Specification

- **REQ-01** — Authentication tokens must expire after 24 hours.
- **REQ-02** — Refresh tokens must be single-use and rotated on each use.

## Traceability

| Requirement | Tests | Implementation | Status |
|-------------|-------|----------------|--------|
| REQ-01 | test_token_expires_after_24h | auth/tokens.py | done |
| REQ-02 | test_refresh_is_single_use | auth/refresh.py | done |
