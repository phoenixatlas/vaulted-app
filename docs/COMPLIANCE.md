# Compliance & Sanctions Screening

Vaulted is subject to UK Money Laundering Regulations 2017 (MLR 2017), the
FATF Travel Rule, and OFAC/UK/EU consolidated sanctions lists. This document
describes how sanctions screening is wired, how to enable full live screening
in production, and the degraded-mode fallbacks.

---

## 1. Architecture Overview

Every KYC-verified user is screened against OFAC/UK/EU/UN sanctions + PEP
(politically-exposed person) lists via **OpenSanctions**.

```
Stripe Identity verified webhook
        │
        ▼
_apply_identity_verified()
        │
        ▼
screen_sanctions(name, dob, country)   ─── OpenSanctions /match/default
        │
        ▼
kyc.sanctions = { matched, degraded, degraded_reason, ... }
        │
        ▼
GET /api/kyc/status  ── surfaces state to the frontend
POST /api/remit/send ── enforces strict-mode gate if enabled
```

Additionally, every send hard-blocks against a **corridor blocklist**
(`COUNTRY_BLOCKLIST` in `compliance.py`): North Korea, Iran, Cuba, Russia,
Syria, Belarus, Myanmar, plus Crimea / DPR / LPR sub-regions.

---

## 2. Environment Variables

| Var | Default | Purpose |
|-----|---------|---------|
| `OPENSANCTIONS_URL` | `https://api.opensanctions.org` | Endpoint to hit. Override for self-hosted Yente. |
| `OPENSANCTIONS_API_KEY` | *(empty)* | Bearer key. Without this, all screens run in **degraded** mode. |
| `COMPLIANCE_STRICT_MODE` | `false` | When `true`, `/api/remit/send` returns 503 if the user's last screen was degraded. Flip on once FCA registration + paid OpenSanctions key are in place. |
| `ADMIN_EMAILS` | *(empty)* | Comma-separated list of admin emails allowed to hit `/api/admin/compliance/*`. |

---

## 3. Getting an OpenSanctions Key

OpenSanctions offers three paths, in ascending order of cost/robustness:

### Path A — Hosted API (paid, easiest)

1. Sign up at <https://www.opensanctions.org/api/>
2. Free keys are issued to **journalists, anti-corruption activists, and
   academic researchers** — commercial fintech use requires a paid plan.
3. Paid tiers (as of 2026):
   - **Free tier**: 5 requests/day (dev only)
   - **Match** (~€250/mo): 100k requests/month + entity retrieval — **recommended for UK remittance at any real volume**
   - **Enterprise**: custom
4. Once you have the key, paste it into `/app/backend/.env`:
   ```
   OPENSANCTIONS_API_KEY=os_live_xxxxxxxxxxxxx
   ```
5. Restart backend: `sudo supervisorctl restart backend`
6. Verify: hit `GET /api/admin/compliance/health` — should return
   `opensanctions.health.status = "live"` and `matched_expected = true`
   (the canary query is "Vladimir Putin" which is on every sanctions list).

### Path B — Self-hosted Yente (£0)

OpenSanctions publishes their engine as an open-source Docker image called
[Yente](https://github.com/opensanctions/yente). It serves the same
`/match/default` API against their public data dump (updated daily).

Minimal Fly.io / Render deploy (~$7/mo instance):
```yaml
# docker-compose.yente.yml
version: "3.7"
services:
  yente:
    image: ghcr.io/opensanctions/yente:latest
    ports: ["8000:8000"]
    volumes: ["yente-data:/data"]
    environment:
      YENTE_ELASTIC_URL: http://elastic:9200
      YENTE_UPDATE_TOKEN: change-me
  elastic:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms512m -Xmx512m"
    volumes: ["es-data:/usr/share/elasticsearch/data"]
volumes:
  yente-data:
  es-data:
```
Then in `/app/backend/.env`:
```
OPENSANCTIONS_URL=https://your-yente-host.fly.dev
OPENSANCTIONS_API_KEY=(leave empty — Yente doesn't require auth)
```
> Note: our current code short-circuits when `OPENSANCTIONS_API_KEY` is empty.
> When you use Yente, temporarily set `OPENSANCTIONS_API_KEY=self-hosted` (or
> any non-empty placeholder) — Yente ignores the header. A follow-up refactor
> should split "key required" from "url is hosted API" as two separate flags.

### Path C — Corridor blocklist only (current default)

If neither API is configured, screening runs in **degraded** mode:
- `kyc.sanctions.matched = false`, `degraded = true`, `degraded_reason = "no_api_key"`
- The corridor blocklist (`COUNTRY_BLOCKLIST`) still hard-blocks sends to
  sanctioned destinations at `/api/remit/quote` and `/api/remit/send`
- FCA-defensible for very early stage, but you must upgrade before applying
  for FCA money-transmission authorisation

---

## 4. Admin Endpoints

All require `ADMIN_EMAILS` to include the caller's email and a valid JWT.

### `GET /api/admin/compliance/health`

Pings OpenSanctions with a canary query ("Vladimir Putin") and returns:
```json
{
  "opensanctions": {
    "config": {
      "url": "https://api.opensanctions.org",
      "api_key_configured": true,
      "strict_mode": false,
      "scopes": ["sanctions", "peps"]
    },
    "health": {
      "ok": true,
      "status": "live",
      "reason": null,
      "latency_ms": 214,
      "matched_expected": true,
      "highest_score": 0.98
    }
  },
  "corridor_blocklist": { "count": 10, "codes": ["BY", "CU", "IR", ...] },
  "checked_at": "2026-07-08T20:14:00Z"
}
```

### `POST /api/admin/compliance/screen`

Manually screen a name against sanctions + PEP lists (bypasses KYC flow).
Useful for ad-hoc SAR investigations.
```json
POST /api/admin/compliance/screen
{ "name": "John Doe", "dob": "1980-01-15", "country": "GB" }
```

---

## 5. Audit Logging

Every call to `screen_sanctions()` emits a structured log line via the
`vaulted.compliance.audit` logger:

```json
{
  "event": "sanctions_screen",
  "name_hash": "3f7c...",       // sha256[:12] — never raw PII
  "name_initial": "J",           // for eyeball scanning only
  "country": "GB",
  "has_dob": true,
  "matched": false,
  "degraded": false,
  "degraded_reason": null,
  "highest_score": 0.62,
  "scope": null,
  "latency_ms": 214,
  "checked_at": "2026-07-08T20:14:00Z"
}
```

Configure your log aggregator (Datadog, Logtail, etc.) to filter on
`event == "sanctions_screen"` for compliance retention.

---

## 6. Enabling Strict Mode

Once you have a live OpenSanctions key AND monitoring in place to alert on
degraded-mode logs, flip strict mode on:

```
COMPLIANCE_STRICT_MODE=true
```

Effect: `/api/remit/send` returns HTTP 503 with `error: "sanctions_screening_unavailable"`
if a user tries to send while their last screen was degraded. This means an
OpenSanctions outage will block ALL sends — make sure you have paging on the
`vaulted.compliance.audit` logs BEFORE flipping this on.
