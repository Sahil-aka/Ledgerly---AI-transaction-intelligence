# Ledgerly — AI transaction intelligence

Ledgerly turns a messy transaction CSV into a searchable analysis with category totals, anomaly flags, and an AI-written summary. Each account has a private workspace; jobs and results are visible only to the account that uploaded them.

## What’s included

- Responsive web app with sign-up, sign-in, CSV upload, processing status, results, and anomaly details.
- FastAPI backend with Argon2 password hashing and 12-hour signed bearer tokens.
- PostgreSQL for users, jobs, cleaned transactions, and summaries; Redis and Celery for asynchronous processing.
- Gemini classification and narrative summaries when `GEMINI_API_KEY` is configured.
- A sample CSV available from the web app.

## Run locally with Docker

Requirements: Docker Desktop with the Linux engine enabled.

1. Copy `.env.example` to `.env` **once**. In PowerShell:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   If `.env` already exists, edit it instead of copying over it. Set `GEMINI_API_KEY` to your Gemini key. Set `JWT_SECRET_KEY` to a long random value; for a live deployment, never use the development fallback.

2. Start the stack from the repository root:

   ```powershell
   docker compose up --build -d
   ```

3. Open the web app at <http://localhost:5173>. The API health endpoint is <http://localhost:8002/health> and API docs are at <http://localhost:8002/docs>.

   If port `5173` is already in use, set `FRONTEND_PORT=5174` in `.env` and rerun Compose. The API is mapped to host port `8002`; PostgreSQL and Redis stay on the private Compose network and do not publish host ports.

4. Create an account, download the sample CSV in the app, upload it, and select the new analysis to see its summary and transactions.

To stop the containers while keeping the PostgreSQL volume:

```powershell
docker compose down
```

`docker compose down -v` deletes the database volume and all saved accounts and analyses. Use it only if you intend to reset the local demo data.

## API authentication

- `POST /auth/signup` accepts `{ "name", "email", "password" }` and returns a bearer token.
- `POST /auth/login` accepts `{ "email", "password" }` and returns a bearer token.
- `GET /auth/me` returns the authenticated account.
- All `/jobs` routes require `Authorization: Bearer <access_token>`.

The web app stores the short-lived access token in tab-scoped session storage and clears it on sign-out or expiry. Passwords are never stored in plain text. Existing jobs created before authentication remain unowned and are not visible to new accounts.

## Live hosting

For a hosted demo, use Render for the API, worker, Redis-compatible queue, and frontend, with Supabase providing managed PostgreSQL. In Render, configure `DATABASE_URL` from the Supabase **Session pooler** connection string and add `sslmode=require`. Render's network is IPv4-only, while Supabase direct connections use IPv6 by default; the Session pooler is the appropriate IPv4 option for this persistent API and worker. Copy the exact host and username from Supabase's Connect dialog, and URL-encode special characters in the database password. [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres)

Set `GEMINI_API_KEY` and a unique random `JWT_SECRET_KEY` as Render secrets. Keep `.env` out of Git and never put server secrets in frontend files. The current API command and bind mounts are tuned for local development; use a production ASGI command and remove the development mounts for public deployment. The frontend currently proxies `/api` to the Compose service name, so its API proxy must be configured for Render's private service address before deployment.

## Data processing

The worker normalizes dates and amounts, removes duplicates, detects outliers and domestic-merchant currency mismatches, classifies uncategorized rows, and stores a summary. Gemini calls can fail independently; classification failures are marked on rows and the summary uses computed totals.
