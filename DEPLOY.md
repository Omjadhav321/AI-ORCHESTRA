# Deploying SmartQueue

This file covers the Docker path, the Cloud VM path and the Kubernetes path. The old
InfinityFree instructions were for the static prototype that now lives in `legacy/`.

## Target topology

```
                        ┌───────────────┐
   Expo app ──HTTPS──▶  │               │
   Dashboard ──HTTPS──▶ │     nginx     │  TLS termination, gzip, rate limits
                        │               │
                        └───┬───────┬───┘
                     /api   │       │  /
                            ▼       ▼
                   ┌────────────┐  ┌──────────────┐
                   │  backend   │  │  dashboard   │  static SPA
                   │ (Express)  │  │  (nginx)     │
                   └─────┬──────┘  └──────────────┘
                         │ /ai
                         ▼
                   ┌─────────────┐        ┌──────────────┐
                   │ ai_service  │        │  MySQL 8.0   │
                   │ (FastAPI)   │        │              │
                   └─────────────┘        └──────────────┘
```

`nginx` terminates TLS and routes `/api` and `/health` to the backend and everything else
to the dashboard. The dashboard calls the API through the same origin, so there is no CORS
preflight in production.

## Prerequisites

- Docker Engine 24+ with the Compose v2 plugin (`docker compose version`).
- A domain with an A record pointing at the host.
- Ports 80 and 443 open; the MySQL and service ports should stay closed to the internet.

## 1. Prepare the host

```bash
sudo mkdir -p /opt/smartqueue && sudo chown "$USER" /opt/smartqueue
cd /opt/smartqueue
git clone <your-repo> .
cp .env.example .env
chmod 600 .env
```

Fill in `.env`:

| Variable | Purpose |
|---|---|
| `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD` | Database credentials |
| `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET` | Generate with `openssl rand -hex 64` |
| `CORS_ORIGINS` | `https://your-domain` |
| `FCM_PROJECT_ID`, `FCM_CLIENT_EMAIL`, `FCM_PRIVATE_KEY` | Firebase service account, optional |
| `RETRAIN_TOKEN` | Guards the ML retrain endpoint |

The Compose file reads `AI_SERVICE_URL`, `DB_*` and `JWT_*` internally, so only the
variables above need to be set at the host level.

## 2. Database

`db/schema.sql` and `db/seed.sql` run automatically on first start of the `db` service
because they are mounted into `/docker-entrypoint-initdb.d`.

To apply them to an existing volume, or to run the user seeding script separately:

```bash
docker compose up -d db
docker compose exec -T db mysql -usmartqueue -p"$MYSQL_PASSWORD" smartqueue < db/schema.sql
docker compose exec -T db mysql -usmartqueue -p"$MYSQL_PASSWORD" smartqueue < db/seed.sql
docker compose run --rm backend node scripts/seed.js
```

`scripts/seed.js` creates the demo accounts. It is idempotent, so re-running it is safe.

`scripts/migrate.js` is also idempotent: every `CREATE TABLE` uses `IF NOT EXISTS`, and
columns added after a database was first created are applied through
`information_schema` checks instead of destructive `ALTER`s. It runs on every release from
the deploy workflow and never drops data.

To deliberately start over and destroy every queue, token and user in the database:

```bash
docker compose run --rm backend node scripts/migrate.js --fresh   # or: npm run migrate:fresh
```

## 3. Start the stack

```bash
docker compose build
docker compose up -d
docker compose ps
```

The AI service trains on first boot (`AUTO_TRAIN_ON_BOOT=true`), which takes roughly a
minute. Watch it come up with:

```bash
docker compose logs -f ai_service
```

Check readiness once the stack is running:

```bash
curl -fsS https://your-domain/health/ready
```

`READY` means MySQL answered. `DEGRADED` means the API is serving traffic but the ML
service is not answering yet; token issuance still works and falls back to a heuristic
wait estimate.

## 4. TLS with certbot

Nginx expects certificates at `/etc/letsencrypt/live/smartqueue/`, so it will not start
before the first certificate exists. Issue one with the webroot method:

```bash
docker compose -f docker-compose.yml -f docker-compose.certbot.yml up -d certbot
docker compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    -d your-domain --agree-tos -m you@example.com --no-eff-email" certbot

docker compose restart nginx
```

Renewal runs every 12 hours inside the certbot container. Add this cron on the host to
reload nginx after a successful renewal:

```
17 3,15 * * * cd /opt/smartqueue && docker compose exec -T nginx nginx -s reload
```

## 5. Updating a release

```bash
cd /opt/smartqueue
git pull
docker compose build
docker compose run --rm backend node scripts/migrate.js
docker compose up -d --remove-orphans
docker image prune -f
```

The GitHub Actions workflow in `.github/workflows/deploy.yml` does exactly this over SSH
when a `v*.*.*` tag is pushed. It needs these repository secrets:

| Secret | Value |
|---|---|
| `VM_HOST`, `VM_USER`, `VM_SSH_KEY` | SSH target for the deploy account |
| `CONTAINER_REGISTRY`, `REGISTRY_USER`, `REGISTRY_TOKEN` | Registry used by `docker-build.yml` |

The workflow copies `release.env` to `/opt/smartqueue/release.env`, migrates, rolls the
services and polls `/health` for up to 150 seconds before failing and logging the backend
logs.

## 6. Local development without TLS

The bundled Nginx config is HTTPS-only, so for local work skip it and use the published
service ports:

```bash
docker compose up -d db ai_service backend dashboard
```

| Service | URL |
|---|---|
| API | `http://localhost:5000` |
| Dashboard | `http://localhost:8080` |
| AI service | `http://localhost:8000/docs` |
| Postman environment | `postman/SmartQueue.postman_environment.json` |

Or run the Node and Vite servers on the host instead of in containers:

```bash
cd backend && npm install && npm run dev
cd dashboard && npm install && npm run dev     # proxies /api to :5000
cd ai_service && pip install -r requirements.txt && python scripts/train_model.py
```

## 7. Kubernetes

`infra/k8s/api.yaml` holds the API and AI deployments with probes, resources and secret
references. `infra/k8s/namespace-secrets.yaml` is a template for the namespace and secrets.

```bash
kubectl create namespace smartqueue
kubectl -n smartqueue create secret generic smartqueue-db \
  --from-literal=host=... --from-literal=user=... \
  --from-literal=password=... --from-literal=database=smartqueue
kubectl -n smartqueue create secret generic smartqueue-jwt \
  --from-literal=access-secret=... --from-literal=refresh-secret=...
kubectl -n smartqueue create secret generic smartqueue-fcm \
  --from-literal=project-id=... --from-literal=client-email=... \
  --from-literal=private-key=...

sed "s|\${GITHUB_REPOSITORY_OWNER}|your-org|; s|\${IMAGE_TAG}|v1.0.0|" \
  infra/k8s/api.yaml | kubectl apply -n smartqueue -f -
```

Delete the template secrets file before committing a real cluster, or replace it with
External Secrets / Sealed Secrets.

## 8. Firebase Cloud Messaging

1. Create a Firebase project and register the Android app `in.acme.smartqueue`.
2. Download `google-services.json` to `mobile/assets/google-services.json` and add
   `"googleServicesFile": "./assets/google-services.json"` back to `android` in
   `mobile/app.json`.
3. Enable the Cloud Messaging API and create a service account key.
4. Put the project id, client email and private key into the backend `.env`. Keep the
   private key on one line with escaped `\n`, or set it as a multi-line value in the
   Compose file.

Without credentials the API still runs. `/api/notifications/register-device` succeeds,
push responses report `skipped: true`, and the mobile app relies on SSE and polling.

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| Nginx will not start | Certificates missing. Issue one with certbot, or remove the `nginx` service locally. |
| `502` on `/api` | `docker compose logs backend`; the API waits for MySQL on start. |
| `READY` never becomes `DEGRADED` | MySQL not initialised. `docker compose logs db`. |
| Predictions show `degraded: true` | `docker compose logs ai_service`; first boot trains the model. |
| Push never arrives | FCM credentials missing or `google-services.json` not added. |
| Dashboard 401s after refresh | `CORS_ORIGINS` must include the dashboard origin, and nginx must be in front of both. |
| CI fails on `npm ci` | Commit lockfiles, or rely on the `npm install` fallback in the workflow. |