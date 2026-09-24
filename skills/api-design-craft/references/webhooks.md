# Webhook Patterns — Receiving Side

Receiver-side patterns for consuming webhooks from external services: endpoint shape, signature verification, idempotency, async processing, local testing, retries. For the sender side — designing the webhooks your own API emits — see [rest-patterns.md § Webhook Design](rest-patterns.md#webhook-design). Back to [SKILL.md](../SKILL.md).

## Core Concepts

A **webhook** is an HTTP callback: an external service sends a POST request to your endpoint when an event occurs. Webhooks invert the polling model -- instead of repeatedly asking "did anything change?", the service tells you.

### Webhook vs Polling

| Aspect | Webhook | Polling |
|--------|---------|---------|
| **Latency** | Near real-time (seconds) | Bounded by poll interval |
| **Efficiency** | No wasted requests | Most requests return "no change" |
| **Complexity** | Public endpoint required, signature validation | Simple HTTP client |
| **Reliability** | Must handle retries, idempotency | Missed events are re-fetched |
| **Best for** | Event-driven workflows, real-time sync | Batch processing, unreliable webhook sources |

## Receiving Webhooks

### Endpoint Design

```python
# FastAPI example
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

@app.post("/webhooks/{provider}")
async def receive_webhook(provider: str, request: Request):
    body = await request.body()
    headers = dict(request.headers)

    # 1. Validate signature
    if not verify_signature(provider, body, headers):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 2. Parse payload
    payload = await request.json()

    # 3. Process asynchronously (return 200 quickly)
    await enqueue_webhook_processing(provider, payload)

    # 4. Acknowledge receipt
    return {"status": "accepted"}
```

### Critical Rules

- **Return 200 quickly**: Most providers retry on non-2xx responses or timeouts (typically 5-30 seconds). Process the payload asynchronously.
- **Validate signatures**: Never trust webhook payloads without verifying the cryptographic signature. This prevents replay attacks and forgery.
- **Handle retries with idempotency**: Providers retry failed deliveries. Use the event ID to deduplicate.
- **Use HTTPS**: Webhook payloads may contain sensitive data. Always use TLS endpoints.
- **Don't assume ordering** — events for one resource can arrive out of order (sender contract: rest-patterns §5).
- **Thin payloads**: fetch the object's current state from the API rather than trusting embedded state (rest-patterns §4).

## Signature Validation

### HMAC-SHA256 (Most Common)

Used by: Stripe, GitHub, Shopify, Slack.

```python
import hashlib
import hmac

def verify_hmac_sha256(
    payload: bytes,
    signature: str,
    secret: str,
    header_prefix: str = "",
) -> bool:
    """Verify HMAC-SHA256 webhook signature."""
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # Strip prefix (e.g., "sha256=" for GitHub)
    actual = signature.removeprefix(header_prefix)
    return hmac.compare_digest(expected, actual)
```

What is signed differs per provider (Stripe signs `{timestamp}.{payload}`; Twilio signs the URL + params with HMAC-SHA1) — prefer the provider SDK's verifier; the generic helper fits raw-body HMAC schemes like GitHub's.

Point-in-time: provider specifics drift — verify against the provider's current docs per [§ Current docs for external APIs](../../software-planning/references/cross-agent-skill-conventions.md#current-docs-for-external-apis) before relying on a row.

### Provider-Specific Headers

| Provider | Signature Header | Format | Secret Source |
|----------|-----------------|--------|---------------|
| **Stripe** | `Stripe-Signature` | `t=timestamp,v1=signature` | Webhook endpoint secret |
| **GitHub** | `X-Hub-Signature-256` | `sha256=hex_digest` | Webhook secret |
| **Shopify** | `X-Shopify-Hmac-SHA256` | Base64-encoded HMAC | API secret key |
| **Twilio** | `X-Twilio-Signature` | Base64-encoded HMAC-SHA1 | Auth token |
| **Slack** | `X-Slack-Signature` | `v0=hex_digest` | Signing secret |

### Stripe Signature Validation

Stripe uses a timestamp + signature scheme to prevent replay attacks:

```python
import stripe

def verify_stripe_webhook(payload: bytes, sig_header: str, secret: str):
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
        return event
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=401, detail="Invalid Stripe signature")
```

Always use the SDK's built-in verification when available -- it handles timestamp tolerance, signature comparison, and edge cases.

## Idempotency

Webhooks are delivered **at least once**. Design for duplicate deliveries.

### Deduplication Strategies

| Strategy | How | Trade-off |
|----------|-----|-----------|
| **Event ID tracking** | Store processed event IDs, skip duplicates | Requires storage, must handle TTL |
| **Idempotent operations** | Design operations so repeating them is harmless | Not always possible (e.g., sending emails) |
| **Database constraints** | Use unique constraints to prevent duplicate inserts | Natural fit for data sync webhooks |

```python
async def process_webhook_idempotently(event_id: str, payload: dict):
    # Check if already processed
    if await event_store.exists(event_id):
        return  # Already processed, skip

    # Process the event
    await handle_event(payload)

    # Mark as processed (with TTL for storage management)
    await event_store.set(event_id, ttl_seconds=86400 * 7)  # 7 days
```

## Event Processing Architecture

### Synchronous (Simple)

Process the webhook inline. Suitable for low-volume webhooks with fast processing.

```
External Service → POST /webhook → Process → 200 OK
```

### Asynchronous (Recommended)

Enqueue for background processing. Return 200 immediately.

```
External Service → POST /webhook → Validate → Enqueue → 200 OK
                                                  ↓
                                            Background Worker → Process
```

Use a task queue (Celery, Bull, Temporal) or a message broker (RabbitMQ, SQS, Cloud Tasks) for the async path.

### Fan-Out

When a single webhook event triggers multiple downstream actions:

```
Webhook received
  → Validate + dedup
  → Publish to internal event bus
    → Handler A (update database)
    → Handler B (send notification)
    → Handler C (sync to analytics)
```

## Local Development

### Tunnel Services

Webhooks require a public URL. During development, use a tunnel:

| Tool | Command | Notes |
|------|---------|-------|
| **ngrok** | `ngrok http 8000` | Free tier, stable URLs on paid plans |
| **Cloudflare Tunnel** | `cloudflared tunnel --url localhost:8000` | Free, no account needed for quick tunnels |
| **localtunnel** | `lt --port 8000` | Open source, less reliable |

### CLI-Based Testing

Some providers offer CLI webhook forwarding:

```bash
# Stripe
stripe listen --forward-to localhost:8000/webhooks/stripe

# GitHub (via smee.io)
smee -u https://smee.io/YOUR_CHANNEL -t http://localhost:8000/webhooks/github
```

### Replay Testing

Save webhook payloads for replay in tests:

```python
# Save incoming webhooks to files during development
import json
from pathlib import Path

async def save_webhook_for_testing(provider: str, payload: dict):
    path = Path(f"tmp/webhooks/{provider}")
    path.mkdir(parents=True, exist_ok=True)
    event_type = payload.get("type", "unknown")
    (path / f"{event_type}.json").write_text(json.dumps(payload, indent=2))
```

## Error Handling and Retry

### Retry Behavior by Provider

Point-in-time: provider specifics drift — verify against the provider's current docs per [§ Current docs for external APIs](../../software-planning/references/cross-agent-skill-conventions.md#current-docs-for-external-apis) before relying on a row.

| Provider | Retry Count | Retry Window | Backoff |
|----------|-------------|-------------|---------|
| **Stripe** | Up to 3 | 3 days | Exponential |
| **GitHub** | 1 | 30 seconds | None |
| **Shopify** | Up to 19 | 48 hours | 10 minutes to 48 hours |
| **Twilio** | Up to 1 | Immediate | None |

### Handling Failures

```python
@app.post("/webhooks/{provider}")
async def receive_webhook(provider: str, request: Request):
    try:
        body = await request.body()
        if not verify_signature(provider, body, dict(request.headers)):
            return JSONResponse(status_code=401, content={"error": "Invalid signature"})

        payload = await request.json()
        await enqueue_webhook_processing(provider, payload)
        return {"status": "accepted"}

    except Exception:
        # Returning 5xx asks the provider to retry -- use it only for transient
        # failures; for payloads you can never process, log and dead-letter them
        # and return 2xx so retries stop.
        logger.exception("Webhook processing error")
        return JSONResponse(status_code=500, content={"error": "Processing failed"})
```

### Dead Letter Queue

For webhooks that fail processing after all retries, route to a dead letter queue for manual inspection:

```python
async def process_with_dlq(event_id: str, payload: dict, attempt: int = 1):
    try:
        await handle_event(payload)
    except Exception as e:
        if attempt >= MAX_RETRIES:
            await dead_letter_queue.put(event_id=event_id, payload=payload, error=str(e))
            logger.error(f"Webhook {event_id} moved to DLQ after {attempt} attempts")
        else:
            raise  # Let the task queue retry
```

## Security Checklist

- [ ] Validate cryptographic signatures on all incoming webhooks
- [ ] Use HTTPS endpoints only
- [ ] Implement timestamp tolerance (reject events older than 5 minutes)
- [ ] Rate-limit the webhook endpoint to prevent abuse
- [ ] Store webhook secrets in environment variables, never in code
- [ ] Log all received events (with payload redaction for PII)
- [ ] Monitor for delivery gaps (compare expected vs received event counts)
- [ ] Handle signature rotation (support multiple active secrets during rollover)
