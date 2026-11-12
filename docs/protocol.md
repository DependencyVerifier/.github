# DependencyVerifier agent protocol — version 1

Normative contract between the **agent** (`depverify-agent`) and the **console**. The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Rationale and context: [`cadrage.md`](cadrage.md) §6 (agent), §6bis (containers), §5ter (limits), §9bis (sizing).

Machine-readable parts: [`protocol/schemas/`](protocol/schemas) (JSON Schema 2020-12), [`protocol/examples/`](protocol/examples) (valid messages, checked by CI) and [`protocol/test-vectors/`](protocol/test-vectors) (signatures to test implementations against).

## 1. Principles

- **Outbound only.** The agent opens every connection (HTTPS); it never listens. The console never calls the agent.
- **Every agent request is signed** with the agent's Ed25519 key (§4). No shared secret travels after enrollment.
- **Every order is signed** with the console's Ed25519 key, **pinned** by the agent at install time (§7).
- **The console drives the pace**: each response says when to come back (`next_poll_in`); `429` / `503` + `Retry-After` always win.
- **Closed order catalogue**: an agent executes only the order types listed in §7.3, never a command or script received from the network.
- **Idempotent, deduplicated inventories**: unchanged content is announced by its digest only (§8).

## 2. Conventions

| Item | Rule |
|---|---|
| Base URL | The console URL given at install (`AGENT_CONSOLE_URL`, e.g. `https://console.depverify.romainmillan.fr`). Each instance has its own; nothing in the protocol depends on a domain. |
| Path prefix | `/agent/v1`. A breaking change gets `/agent/v2`; both may be served during a transition. |
| `protocol_version` | Integer `1`, in every request body. |
| Encoding | JSON, UTF-8, `Content-Type: application/json`. Snapshot uploads: see §8.3. |
| Timestamps | RFC 3339, UTC, second precision, `Z` suffix: `2026-11-09T08:00:00Z`. |
| Identifiers | UUID v7 strings (`agent_id`, `order_id`, `inventory_id`). |
| Digests | `sha256:` + 64 lowercase hex characters, over the exact bytes described. |
| Keys | Ed25519. Public key text form: `ed25519:` + standard base64 of the raw 32 bytes. |
| Key fingerprint / key id | `SHA256:` + standard base64, **without padding**, of SHA-256(raw 32-byte public key), as `ssh-keygen -l` prints it. Shown to humans for approval. |
| Unknown fields | Receivers MUST ignore fields they do not know (additive minor revisions). The schemas describe exactly what a v1 producer sends. |
| User agent | `User-Agent: depverify-agent/<version> (<os>; <arch>)`. |

## 3. Transport

- HTTPS only, TLS 1.2 or later, certificate validated against the system roots (or a CA bundle configured at install). The agent uses rustls; it MUST NOT disable certificate verification.
- HTTP proxies: the agent honours `HTTPS_PROXY` / `NO_PROXY`.
- Request bodies are at most **1 MiB** of JSON, except snapshot uploads (§8.3).
- The agent's HTTP client timeout is at least **75 s**, so that the console MAY hold a poll open (long polling, §6.2).
- Redirects are not followed (a redirect is a misconfiguration; report it and back off).

## 4. Request signatures (profile `depverify-agent-v1`)

Every request to `/agent/v1/*` carries an HTTP Message Signature (RFC 9421) made with the agent's private key. The profile below is fixed: a console MUST reject any request that deviates from it.

### 4.1 Headers

| Header | Value |
|---|---|
| `Date` | IMF-fixdate of the moment of signing (`Mon, 09 Nov 2026 08:00:00 GMT`). |
| `Content-Digest` | RFC 9530, `sha-256=:<base64>:` of the request content **as sent** (after `Content-Encoding`). Required when the request has a body; absent otherwise. |
| `Signature-Input` | One signature, labelled `sig1`, with the parameters of §4.2. |
| `Signature` | `sig1=:<base64 Ed25519 signature>:` |

### 4.2 Covered components and parameters

- Covered components, **in this order**: `"@method" "@target-uri" "content-digest" "date"`. Without a body: `"@method" "@target-uri" "date"`.
- Parameters, **in this order**:
  - `created`: Unix time of signing;
  - `expires`: `created` + at most 300;
  - `keyid`: the agent key fingerprint (§2);
  - `alg="ed25519"`;
  - `nonce`: at least 16 random bytes, base64url without padding, never reused;
  - `tag="depverify-agent-v1"`.
- The signature base is built exactly as RFC 9421 §2.5 describes (one line per component, `\n` separators, no trailing newline).

```text
Signature-Input: sig1=("@method" "@target-uri" "content-digest" "date");created=1794211200;expires=1794211500;keyid="SHA256:If4x36FUomFia/hUBG/SJxt77UtqvkWqWId+9H+XIbk";alg="ed25519";nonce="aw89HJouS3-MXR4vOktcbQ";tag="depverify-agent-v1"
```

A complete signed request, with its key and signature base, is in [`protocol/test-vectors/request-signature.json`](protocol/test-vectors/request-signature.json). Implementations MUST reproduce it byte for byte.

### 4.3 Verification by the console

In this order, stopping at the first failure:

1. `Signature-Input` and `Signature` are present, hold exactly one label `sig1`, the covered components and parameters match §4.2, `tag` is `depverify-agent-v1`, `alg` is `ed25519`. Otherwise: `invalid_signature`.
2. `created` is within **±300 s** of the console clock and `expires` ≤ `created` + 300 and not in the past. Otherwise: `clock_skew` (with `server_time`).
3. `Content-Digest` matches the received content (before decoding). Otherwise: `invalid_digest`.
4. The `keyid` belongs to a known agent (or, for enrollment, to the public key in the body: §5). Otherwise: `unknown_agent`.
5. The Ed25519 signature verifies with that public key. Otherwise: `invalid_signature`.
6. The (`keyid`, `nonce`) pair has not been seen in the last **10 minutes**. Otherwise: `replayed_request`. The console keeps nonces for at least 10 minutes.
7. Agent state allows the endpoint (§6.3). Otherwise: `agent_pending` or `agent_revoked`.

Failures are recorded in the audit log (agent, endpoint, reason, IP); bodies are never logged.

### 4.4 Clock

The agent SHOULD keep an offset to the console clock, learnt from `server_time` (present in every response and in `clock_skew` problems), and sign with `created` = local time + offset. It MUST NOT retry the same request with the same `nonce`.

## 5. Enrollment

### 5.1 Request

`POST /agent/v1/enrollments`, signed with the **new** agent key (proof of possession). The console takes the public key from the body and checks that `keyid` is its fingerprint.

| Field | Content |
|---|---|
| `enrollment_token` | The token given at install (`AGENT_TOKEN` / `AGENT_TOKEN_FILE`). Sent only here, never logged by either side. |
| `public_key` | `ed25519:…` |
| `agent_version` | Semver of the binary. |
| `mode` | `host` · `container` (MVP), `embedded` · `ecs` (later). |
| `scope` | `container` mode only: `compose` · `labeled` · `host`. |
| `compose_project` | `compose` / `labeled` scopes: the `com.docker.compose.project` label of the agent's own container. The console later rejects inventories outside it (§8.4). |
| `host` | Short host facts: `hostname`, `os` (`id`, `version_id`, `pretty_name`), `kernel`, `arch`, `docker_engine_id` (when Docker is readable), `machine_id_hash` (SHA-256 of `/etc/machine-id`, hex, when readable). Used to group agents of one host. |

Example: [`protocol/examples/enrollment-request.json`](protocol/examples/enrollment-request.json).

### 5.2 Response

`201 Created` (new agent) or `200 OK` (the same token and public key were already enrolled: retries are idempotent).

| Field | Content |
|---|---|
| `agent_id` | UUID v7, stored by the agent. |
| `status` | `pending` (single-use token, or reusable token not yet approved) or `approved` (approved reusable token). |
| `fingerprint` | The agent key fingerprint, as the console shows it to the approver. The agent logs it so the person installing can compare. |
| `console_key_id` | Fingerprint of the console signing key. The agent MUST check it equals the key pinned at install, and refuse to go on otherwise (`console_key_mismatch`, logged, no retry). |
| `next_poll_in` | Seconds before the first poll. |
| `server_time` | Console clock. |

Errors: `token_invalid` (unknown, used or revoked token), `token_expired`, `quota_exceeded` (team `maxAgents`), `invalid_payload`. A single-use token is consumed by the first successful enrollment.

## 6. Polling

### 6.1 Request

`POST /agent/v1/poll`, signed. The agent polls when `next_poll_in` elapses, plus a random jitter of ±10 %.

| Field | Content |
|---|---|
| `agent_version` | Current binary version. |
| `config_version` | Last `SET_CONFIG` version applied (0 before any). |
| `order_results` | Results of orders handled since the last poll (§7.5); empty array otherwise. Sent again until a poll succeeds. |

### 6.2 Response

`200 OK`:

| Field | Content |
|---|---|
| `status` | `pending` or `approved`. |
| `orders` | Signed orders to execute (§7), oldest first. Always empty while `pending`. |
| `next_poll_in` | Seconds, 30–3600. The agent MUST NOT poll sooner, except to report a finished `SCAN_NOW` inventory. |
| `server_time` | Console clock. |

The console MAY hold the request open up to **60 s** and answer as soon as an order is available (long polling, §9bis of the cadrage). Agents need no change for it.

### 6.3 Agent states

| State (console side) | Poll | Inventory endpoints | Orders |
|---|---|---|---|
| `pending` | `200`, `status: pending` | `403 agent_pending` | none |
| `approved` | `200` | allowed | delivered |
| `inactive` (no report for 7 days) | the next valid request makes it `approved` again, if the team quota allows (`quota_exceeded` otherwise) | | |
| `revoked` | `401 agent_revoked` | `401 agent_revoked` | none |

On `agent_revoked` the agent stops contacting the console and logs it; only a new installation (new key, new token) brings it back.

## 7. Orders

### 7.1 Envelope

```json
{
  "order": {
    "order_id": "019a6b2e-7c40-7d3e-9f1a-2b3c4d5e6f70",
    "type": "SET_CONFIG",
    "agent_id": "019a6b2c-1f00-7a11-8b22-3c44d55e6f01",
    "issued_at": "2026-11-09T08:00:00Z",
    "not_before": "2026-11-09T08:00:00Z",
    "expires_at": "2026-11-09T08:15:00Z",
    "payload": { "config_version": 3, "scan_interval_minutes": 360 }
  },
  "signature": { "alg": "ed25519", "key_id": "SHA256:…", "value": "<base64url>" }
}
```

`signature.value` is the Ed25519 signature, by the console signing key, of the **RFC 8785 (JCS) canonical JSON** of `order`, base64url without padding. Vector: [`protocol/test-vectors/order-signature.json`](protocol/test-vectors/order-signature.json).

### 7.2 Verification by the agent

An order is executed only if **all** hold, else it is rejected with the reason in brackets:

1. `signature.alg` is `ed25519`, `signature.key_id` is the pinned console key, and the signature verifies over JCS(`order`) [`bad_signature`].
2. `order.agent_id` is this agent [`wrong_agent`].
3. `not_before` ≤ now ≤ `expires_at` (now = local clock + offset, ±60 s tolerance), and `expires_at` − `issued_at` ≤ **15 minutes** [`expired`].
4. `order_id` is not in the anti-replay store [`replayed`]. The store is **persisted** (it survives restarts) and keeps each id until `expires_at` + 10 minutes.
5. `type` is in the catalogue below [`unknown_type`], and `payload` matches its schema [`invalid_payload`].

### 7.3 Catalogue (v1)

| Type | Payload | Effect |
|---|---|---|
| `SCAN_NOW` | `{}` | Runs a full inventory now (§8). The console rate-limits it to one per agent every 5 minutes. |
| `SET_CONFIG` | `config_version` (integer, increasing), `scan_interval_minutes` (5–10080), `discovery_roots`, `declared_paths`, `exclusions` (absolute paths; exclusions are glob patterns) | Replaces the collection settings. An order whose `config_version` ≤ the applied one is acknowledged without effect. The console never sends an interval below the team's `minScanIntervalMinutes`. |

Reserved for later versions (an agent of this version rejects them as `unknown_type`): `UPGRADE_AGENT` (binary verified with the **project release key** embedded in the agent, never the console key), `ROTATE_KEY` (new agent key pair), `ROTATE_CONSOLE_KEY` (new console key, signed by the **current** one).

### 7.4 Execution

Orders are executed one at a time, in the order received. A second `SCAN_NOW` while an inventory is running is executed as a no-op (`executed`, reason `already_running`).

### 7.5 Results

Each handled order produces one entry in the next poll's `order_results`:

| Field | Content |
|---|---|
| `order_id` | The order. |
| `status` | `executed` · `failed` (accepted but could not finish) · `rejected` (failed §7.2). |
| `reason` | Required unless `executed`: a §7.2 code, or a short machine code (`already_running`, `scan_error`…). |
| `finished_at` | Timestamp. |

## 8. Inventory

An inventory is one collection run: the host facts plus one CycloneDX SBOM per subject (application instance or container image). It is sent in three steps; unchanged content costs one small request.

### 8.1 Snapshots and digests

A **snapshot** is one document, identified by the SHA-256 of its uncompressed bytes:

| Format (`media_type`) | Content |
|---|---|
| `application/vnd.depverify.host-facts+json;version=1` | Host facts ([schema](protocol/schemas/host-facts.schema.json)): OS, kernel, architecture, runtimes, Docker engine, agent settings. |
| `application/vnd.cyclonedx+json;version=1.6` | CycloneDX 1.6 SBOM of one subject, profile §8.5. |

The agent produces snapshots deterministically (stable ordering of components and keys, no timestamps inside the document), so that unchanged content gives an unchanged digest.

### 8.2 Step 1: manifest

`POST /agent/v1/inventories`, signed.

| Field | Content |
|---|---|
| `inventory_id` | UUID v7 chosen by the agent. Retrying the same manifest with the same id is idempotent. |
| `trigger` | `scheduled` · `scan_now` · `image_change` · `startup`. |
| `started_at`, `completed_at` | Collection window. |
| `host_facts` | `{digest, size, media_type}` of the host facts snapshot. |
| `subjects` | One entry per subject: `subject_key`, `kind`, its own fields (below) and `sbom` (`{digest, size, media_type}`). |

Subjects:

| `kind` | `subject_key` | Fields |
|---|---|---|
| `path` | `path:<absolute path>` | `path`, `origin` (`discovered` · `declared`), optional `runtime` (`name`, `version`, `service`, e.g. `php8.2-fpm`) |
| `compose_service` | `compose:<project>/<service>` | `compose_project`, `service`, `container_ids`, `image_id`, optional `labels` (the `dev.depverify.*` labels found: `name`, `environment`, `paths`) |
| `container` | `container:<name>` | standalone container: `container_name`, `container_id`, `image_id` |
| `container_image` | `image:<image id>` | `image_id` (`sha256:…`, also for local builds), `repo_digests`, `tags`, `provenance` (`registry` · `local-build`), optional `base_image` |
| `host` | `host` | none: the SBOM lists the OS packages of the host itself (dpkg, rpm, apk). At most one, sent only by an agent that sees the host (mode `host`, or `container` with scope `host`). |

An application subject running in a container references its image by `image_id`; the image's own packages are in the `container_image` subject's SBOM, analysed once per image id (§6bis of the cadrage).

Response `200 OK`: `inventory_id`, `missing` (digests the console does not have yet; empty when nothing changed), `next_poll_in`, `server_time`.

### 8.3 Step 2: upload missing snapshots

`PUT /agent/v1/inventories/{inventory_id}/snapshots/{digest}`, signed, one per missing digest.

- Body: the snapshot, gzip-compressed. Headers `Content-Type: <media_type>`, `Content-Encoding: gzip`, `Content-Digest` over the **compressed** bytes (§4.1).
- At most **20 MB compressed** (`payload_too_large`); the console also stops decompressing after 200 MB (`payload_too_large`).
- The console checks that SHA-256 of the decompressed bytes equals `{digest}` (`digest_mismatch`) and that the document matches its format.
- `201 Created`, or `200 OK` if already stored. Uploads may run in parallel (at most 4).

### 8.4 Step 3: complete

`POST /agent/v1/inventories/{inventory_id}/complete`, signed, body `{"protocol_version": 1}`.

- `409 missing_snapshots` (with the list) if a digest from `missing` was not uploaded.
- `202 Accepted` otherwise: the console stores the inventory and processes it asynchronously (diff, matching, notifications). The API itself does no matching.
- Scope guard: for `compose` / `labeled` scopes, a subject whose `compose_project` differs from the enrolled one, or a `host` subject, makes the whole inventory rejected (`403 scope_violation`, audited). The console checks it on the manifest already, before anything is stored.
- A manifest not completed within 1 hour is discarded.

### 8.5 CycloneDX profile

- `bomFormat: "CycloneDX"`, `specVersion: "1.6"`, `version: 1`, **no `serialNumber`**: an identifier that changes with each inventory would change the digest of unchanged content and defeat the deduplication of §8.1.
- `metadata.component`: the subject (type `application` or `container`, `name`, `bom-ref` = `subject_key`).
- Every component has a `purl`: `pkg:deb/debian/openssl@3.5.1-1?arch=amd64&distro=debian-13`, `pkg:rpm/…`, `pkg:apk/alpine/…`, `pkg:composer/symfony/http-kernel@6.4.3`, `pkg:npm/%40hotwired/turbo@8.0.23`.
- Properties, namespace `depverify:`:
  - `depverify:dependency` = `direct` · `transitive`;
  - `depverify:source` = the file the data came from (`vendor/composer/installed.json`, `composer.lock`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `/var/lib/dpkg/status`, `/lib/apk/db/installed`, `rpmdb`);
  - `depverify:package-manager` = `composer` · `npm` · `yarn` · `pnpm` · `dpkg` · `rpm` · `apk`.
- `dependencies` MAY be present; the console does not require it in v1.
- No timestamps, hostnames or secrets inside the SBOM (determinism, §8.1).

## 9. Errors

Errors are RFC 9457 problem documents (`Content-Type: application/problem+json`), [schema](protocol/schemas/problem.schema.json):

```json
{ "type": "urn:depverify:problem:clock_skew", "title": "Request time outside the accepted window", "status": 401, "server_time": "2026-11-09T08:00:00Z" }
```

| Code (`urn:depverify:problem:<code>`) | Status | Agent reaction |
|---|---|---|
| `invalid_payload`, `unsupported_protocol_version` | 400 | Log, report, back off (do not resend unchanged). |
| `invalid_signature`, `invalid_digest`, `replayed_request` | 401 | Log; retry once with a fresh signature, then back off. |
| `clock_skew` | 401 | Recompute the clock offset from `server_time`, retry once. |
| `unknown_agent` | 401 | Log; stop (the console no longer knows this key). |
| `agent_revoked` | 401 | Stop (§6.3). |
| `token_invalid`, `token_expired` | 401 | Stop enrollment; a new token is needed. |
| `agent_pending`, `scope_violation` | 403 | `agent_pending`: keep polling. `scope_violation`: log, next scheduled run. |
| `not_found` | 404 | Log, back off. |
| `missing_snapshots` | 409 | Upload the listed digests, complete again. |
| `payload_too_large`, `digest_mismatch` | 413 / 422 | Log; skip that snapshot until the next run. |
| `quota_exceeded` | 409 | Log; retry at the next poll interval. |
| `rate_limited` | 429 | Wait `Retry-After`. |
| (any) | 5xx | Exponential backoff with jitter, 30 s up to 1 h; honour `Retry-After`. |

## 10. Limits

| Limit | Value | Source |
|---|---|---|
| Requests per agent | 60 / minute (`429` + `Retry-After` beyond) | cadrage §5ter |
| JSON request body | 1 MiB | |
| Snapshot | 20 MB compressed, 200 MB decompressed | cadrage §5ter |
| Signature validity | `created` ±300 s, `expires` ≤ `created` + 300 | |
| Nonce memory (console) | 10 minutes | |
| Order validity | ≤ 15 minutes | cadrage §6 |
| `SCAN_NOW` | 1 per agent every 5 minutes | cadrage §5ter |
| Poll interval | `next_poll_in` 30–3600 s, ±10 % jitter | cadrage §9bis |
| Uncompleted manifest | discarded after 1 hour | |

## 11. Install-time material (agent side)

| Setting | Content |
|---|---|
| `AGENT_CONSOLE_URL` | Base URL (§2). |
| `AGENT_CONSOLE_PUBKEY` | `ed25519:…`, written in `install.sh` or the generated Compose snippet: the **pinned** console key. |
| `AGENT_TOKEN` / `AGENT_TOKEN_FILE` | Enrollment token, read once. |
| State directory | `/var/lib/depverify-agent` (host) or `/var/lib/agent` (container volume): private key (`0600`), `agent_id`, console clock offset, applied `config_version`, anti-replay store. Losing it means enrolling again. |

## 12. Security notes

- TLS protects confidentiality; signatures protect authenticity and integrity even behind TLS-terminating proxies.
- A compromised console can send only catalogue orders: it can make an agent scan or change its paths, never run code or change the binary (upgrades are verified with the project release key, §7.3).
- The enrollment token is the only secret ever sent; it is single-use (or bounded and human-approved when reusable) and never logged.
- Nothing in a request identifies people; host facts carry a hash of the machine id, not the id itself.
