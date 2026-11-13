# Webhooks of DependencyVerifier

A team calls its own HTTPS endpoints when the rules that name them retain an event (cadrage, decisions 58–64). This
document is the contract of those calls: what is sent, how it is signed, how a receiver checks it.

## Delivery

- `POST` to the URL of the webhook, **HTTPS only**, never to a private network (loopback, RFC 1918, link-local…),
  **no redirect followed**, 10 s timeout.
- Any `2xx` answer is a success; anything else (another status, a timeout, a refused connection) is a failure, tried
  again after 1, 5, 25 then 125 minutes, then given up. The answer body is never read.
- One request per event and rule: an event retained by two rules calling the same webhook arrives twice (two
  `delivery` ids). A retry keeps the same `delivery` id: a receiver deduplicates on it.

## Headers

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `X-DepVerify-Event` | the event, see below |
| `X-DepVerify-Delivery` | the id of the delivery (UUID), the same on every retry |
| `X-DepVerify-Timestamp` | Unix time of this attempt, in seconds |
| `X-DepVerify-Signature` | `sha256=` + hexadecimal HMAC-SHA256 of `timestamp + "." + body`, keyed by the secret |

The secret (`whsec_…`) is shown once, when the webhook is created or given a new secret. A new secret stops the
former one at once.

## Body (version 1)

```json
{
  "version": 1,
  "id": "019a6b2c-…",
  "delivery": "019a6b2d-…",
  "event": "vulnerability_opened",
  "occurred_at": "2026-11-13T09:00:00+00:00",
  "team_id": "019a6b2c-…",
  "project_id": "019a6b2c-…",
  "data": { }
}
```

`id` is the notice (one per rule and occurrence); `project_id` is `null` for the fleet of the team. New fields may be
added to `data` and to the envelope without a new version; a field is never removed or changed within version 1.

### Events and their `data`

| `event` | `data` |
|---|---|
| `vulnerability_opened`, `vulnerability_fixed`, `end_of_life`, `outdated` | `change` (`opened`, `reopened`, `fixed`, `escalated`), `finding` (`id`, `kind`, `title`, `package`, `installed`, `fixed`, `severity`, `cvss`, `known_exploited`, `epss`, `eol_level`, `end_of_life`, `suggested`, `latest`, `aliases`), `subject` (`type`: `application` or `host`, `id`, `name`), `project_id`, `environment_id` |
| `agent_pending` | `agent` (`id`, `hostname`) |
| `agent_silent` | `agent` (`id`, `hostname`, `last_seen_at`) |
| `acceptance_expiring` | `acceptance` (`id`, `expires_on`), `finding` (`id`, `kind`, `title`, `package`), `subject`, `project_id`, `environment_id` |
| `test` | `{}` (the "Send a test" button) |

## Checking a request

1. Read the raw body, before any JSON decoding.
2. Refuse a timestamp more than 5 minutes away from now (replay).
3. Compute `sha256=` + HMAC-SHA256(secret, timestamp + "." + body) and compare it to the header in constant time.
4. Deduplicate on `X-DepVerify-Delivery`.

```php
$body = file_get_contents('php://input');
$timestamp = $_SERVER['HTTP_X_DEPVERIFY_TIMESTAMP'] ?? '';
$expected = 'sha256='.hash_hmac('sha256', $timestamp.'.'.$body, $secret);
if (abs(time() - (int) $timestamp) > 300 || !hash_equals($expected, $_SERVER['HTTP_X_DEPVERIFY_SIGNATURE'] ?? '')) {
    http_response_code(401);
    exit;
}
```

```python
import hashlib, hmac, time

def verify(secret: bytes, timestamp: str, body: bytes, signature: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:
        return False
    expected = "sha256=" + hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Test vector: secret `whsec_test`, timestamp `1700000000`, body `{"version":1}` give
`sha256=83171cbb758ad8691565f1c3f7f4593a985a0451a5e67181aba825c6a58bb106`.
