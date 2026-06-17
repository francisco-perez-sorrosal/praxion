---
diataxis: how-to
audience: [human, agent]
---

# Authentication

<!-- aac:authored owner=unspecified -->
How to obtain, present, and rotate credentials. Document the scheme explicitly —
an agent cannot infer your auth model from the spec alone.

## Scheme

State the scheme: `Bearer` token / API key header / OAuth2 / mTLS.

## Obtaining a credential

Step-by-step: where to register, where the key/token appears, scopes.

## Presenting the credential

```
Authorization: Bearer <token>
```

## Rotation and expiry

Token lifetime, refresh flow, and what a `401` means (see [Errors](errors.md)).
<!-- aac:end -->

<!-- aac:generated source=<spec> view=securitySchemes -->
<!--
  The securitySchemes section of the spec renders here. Regenerated from the
  committed spec by the docs pipeline — do not hand-edit inside this fence.
  Until the generator is wired, this fence is an empty placeholder.
-->
<!-- aac:end -->
