# Security

Status: the rules in "Always" apply **now**, to all code including the legacy prototype. Everything else is **Planned** for the FastAPI backend (ADR-008 in [decisions.md](decisions.md)).

## Always

- Never commit secrets, API keys, tokens, credentials, `.env*` files (except `.env.example`), `.streamlit/secrets.toml`, database dumps, or production config. `.gitignore` already covers `.env` and `.streamlit/secrets.toml`; extend it as new secret files appear.
- Examples use placeholders such as `<TMDB_API_KEY>`, never real-looking values.
- If a secret is committed by accident, stop and tell the user. The secret must be rotated; rewriting history does not undo the leak.
- Do not log passwords, tokens, cookies, `Authorization` headers, password-reset links, or full request bodies of auth endpoints.
- Do not run destructive database operations (DROP, TRUNCATE, mass UPDATE/DELETE, destructive migrations, restoring over a database) without explicit user approval.

## Authentication (planned)

| Item | Rule |
|---|---|
| Password hashing | Argon2id via `pwdlib`. Minimum password length 8, maximum 128, checked against a common-password list |
| Access token | JWT, HS256 (or EdDSA), lifetime **15 min**. Claims: `sub` (user uuid), `exp`, `iat`, `jti`. No PII |
| Refresh token | Opaque random 256-bit value, lifetime **30 days**. Only the SHA-256 hash is stored in `refresh_tokens` |
| Rotation | Every `/auth/refresh` revokes the presented token, issues a new one in the same `family_id`, and sets `replaced_by_id` |
| Reuse detection | If a refresh token that is already revoked is presented, revoke the **whole family** and return 401. This signals likely token theft |
| Logout | Revoke the current family and clear the cookies. `logout-all` revokes every family for the user |
| Password change or reset | Revoke all of the user's refresh tokens |
| OAuth (Google) | Authlib, `state` + PKCE. Link by verified email only |
| Email verification and reset tokens | Random single-use tokens, hashed in the DB, 30–60 min expiry |

### Cookies

| Cookie | Attributes |
|---|---|
| `access_token` | `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=900` |
| `refresh_token` | `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=2592000` |
| `csrf_token` | `Secure; SameSite=Lax; Path=/` (readable by JS, **not** HttpOnly) |

`Secure` may be disabled only for local development over http, through a setting that defaults to secure.

### CSRF

Use double-submit: every mutating request (POST/PUT/PATCH/DELETE) that is authenticated by cookie must send `X-CSRF-Token` equal to the `csrf_token` cookie. A mismatch returns 403. SameSite=Lax is defense in depth, not a replacement.

### CORS

Use an explicit allow-list of frontend origins with `allow_credentials=True`. Never use `*` together with credentials.

## Authorization

- Enforce authorization in the backend service layer. Frontend checks are only for UX.
- Writes act on `current_user.id` and never take a client-supplied user id.
- Reviews, lists, and recommendation submissions can be edited only by their owner or an admin.
- Private entries (`is_private`) and private custom lists are hidden from everyone except the owner.
- Admin endpoints require `is_admin`. The admin UI (sqladmin) sits behind admin auth and is not publicly linked.

## Input validation

- Every request body and query parameter is validated with a Pydantic schema: bounded string lengths, numeric ranges (score 1–10, page_size ≤ 100), enums for status and sort fields.
- Use the SQLAlchemy ORM or bound parameters only. Never build SQL with string formatting.
- Treat user text (reviews, notes) as plain text. React escapes it on render; never use `dangerouslySetInnerHTML` for user content.
- Validate and allow-list sort and filter fields before passing them to Meilisearch or SQL.

## Rate limiting (planned, Redis-backed)

| Endpoint | Limit |
|---|---|
| `/auth/login` | 5/min per IP + username, 20/hour per IP |
| `/auth/register`, `/auth/password/forgot` | 5/hour per IP |
| `/auth/refresh` | 30/min per user |
| `/search` | 60/min per IP |
| `/search/suggest` (autocomplete, called per keystroke after debounce) | 300/min per IP |
| Review, user-rec, and list writes | 30/min per user |
| `/events` | 120/min per session |

Exceeding a limit returns 429 with `Retry-After`.

## Transport and headers

- HTTPS only (Caddy). HSTS is enabled.
- Headers: CSP, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `frame-ancestors 'none'`.
- The legacy `start.sh` sets `enableXsrfProtection = false`. Do not copy that setting into new code.

## Environment variables (example, placeholders only)

Current templates: [apps/api/.env.example](../../apps/api/.env.example), [apps/web/.env.example](../../apps/web/.env.example), and [infra/.env.example](../../infra/.env.example) for compose credentials. The full planned set is below. Add each variable to the relevant template, and to `app/core/config.py`, in the change that starts using it. Never commit a real `.env`.

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://<DB_USER>:<DB_PASSWORD>@localhost:5432/<DB_NAME>
REDIS_URL=redis://localhost:6379/0
MEILI_URL=http://localhost:7700
MEILI_MASTER_KEY=<MEILI_MASTER_KEY>
MEILI_SEARCH_KEY=<MEILI_SEARCH_ONLY_KEY>
JWT_SECRET=<RANDOM_64_BYTE_SECRET>
ACCESS_TOKEN_TTL_SECONDS=900
REFRESH_TOKEN_TTL_SECONDS=2592000
COOKIE_SECURE=true
CORS_ORIGINS=http://localhost:3000
CATALOG_DATA_DIR=../../data
GOOGLE_CLIENT_ID=<GOOGLE_CLIENT_ID>
GOOGLE_CLIENT_SECRET=<GOOGLE_CLIENT_SECRET>
SENTRY_DSN=<SENTRY_DSN>
```
