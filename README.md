# SmartQueue

Queue and token management for government offices and hospitals. Citizens take a token
from their phone and watch their turn live, counter staff run the queue from a browser
dashboard, and a scikit-learn service estimates the wait the moment a token is issued.

```
Expo app (citizens)  ─┐
                      ├─▶ nginx ─▶ Express API ─▶ MySQL 8
React dashboard ──────┘                │
                                       └─▶ FastAPI + scikit-learn
```

## Components

| Path | Stack | Role |
|---|---|---|
| `mobile/` | Expo, React Native, React Navigation | Citizen app: token issue, live status, history, push notifications |
| `dashboard/` | React 18, Vite, React Router | Staff console: queue board, analytics, model card, administration |
| `backend/` | Node 20, Express, JWT, mysql2, firebase-admin | REST API, auth, queue state machine, SSE, FCM, analytics |
| `ai_service/` | Python 3.11, FastAPI, pandas, scikit-learn | Wait-time regression and triage classification |
| `db/` | MySQL 8 | Schema and seed data |
| `infra/` | Nginx, Kubernetes, certbot | Reverse proxy, TLS, cluster manifests |
| `postman/`, `docs/` | Postman, OpenAPI | API exploration and reference |
| `legacy/` | Static HTML | The original prototype, kept for reference only |

## Quick start

```bash
git clone <your-repo> smartqueue && cd smartqueue
cp .env.example .env          # then edit the passwords and JWT secrets

docker compose up -d          # MySQL, AI service, API, dashboard, nginx
docker compose logs -f ai_service   # first boot trains the model, ~1 minute

docker compose run --rm backend node scripts/migrate.js   # schema + seed, idempotent
docker compose run --rm backend node scripts/seed.js      # demo accounts
```

Nginx expects a TLS certificate, so for a first run on your own machine either use
`docker compose up -d db ai_service backend dashboard` and hit the published ports, or
follow the certbot steps in [DEPLOY.md](DEPLOY.md).

| Service | Local URL |
|---|---|
| API | `http://localhost:5000` |
| Dashboard | `http://localhost:8080` |
| ML service docs | `http://localhost:8000/docs` |

## Demo accounts

`scripts/seed.js` and `db/seed.sql` create these, all with the password `Queue@1234`:

| Email | Role | Scope |
|---|---|---|
| `citizen@example.com` | citizen | Takes and tracks tokens |
| `officer@dco.gov.in` | staff | Deputy Commissioner Office counters |
| `doctor@cgh.gov.in` | staff | Central Government Hospital |
| `admin@smartqueue.in` | admin | All facilities, staff and model |

Change the demo passwords before exposing the app to anyone.

## How the queue works

1. A citizen registers or signs in and picks a department.
2. The API computes `peopleAhead` inside a transaction, inserts the token with status
   `waiting`, then asks the ML service for a wait estimate and a triage level.
3. If the ML service is unreachable the API falls back to a heuristic
   (`peopleAhead × avgServiceMinutes ÷ counters`) and flags the result `degraded: true`.
4. Staff call the next token. Selection is priority descending, then oldest first, inside
   a transaction with a `FOR UPDATE` lock.
5. Status moves `waiting → called → serving → completed`, or `→ cancelled` from the app.
   Illegal transitions return `409`.
6. Every transition writes a row to `token_events`, publishes an in-process event, and the
   dashboard and app receive it over SSE. Both clients poll as a fallback if the stream
   drops.
7. The AI service pushes an FCM notification when a citizen is within
   `NOTIFY_PEOPLE_AHEAD` of the counter.

Predictions are recorded on the token, so the dashboard can show real prediction error
alongside the model's reported metrics.

## The ML service

Two models are trained from a synthetic but structurally realistic queue dataset:

- `GradientBoostingRegressor` predicts wait minutes from people ahead, priority, counter
  count, average service time, hour of day, age band and visit type.
- `RandomForestClassifier` predicts triage (`routine`, `urgent`, `critical`).

`AUTO_TRAIN_ON_BOOT=true` trains on startup if no artifact exists, and writes
`queue_model.joblib` plus `metrics.json` to `artifacts/`. `GET /model-info` returns the
model card the dashboard renders. Retraining is available to admins through
`POST /api/ai/retrain`, guarded by `RETRAIN_TOKEN`.

## API surface

Full reference in [`docs/openapi.yaml`](docs/openapi.yaml); an executable collection with
chained journeys is in [`postman/SmartQueue.postman_collection.json`](postman/SmartQueue.postman_collection.json).

| Group | Highlights |
|---|---|
| `/api/auth` | register, login, refresh rotation, logout, me, change-password |
| `/api/tokens` | issue, active, history, by code, cancel, department queue, call-next, status, SSE streams |
| `/api/facilities` | facilities, departments, staff departments, analytics, SSE stream |
| `/api/ai` | predict, triage, model-info, availability, admin retrain |
| `/api/notifications` | register-device, my-devices, test, admin broadcast |
| `/api/admin` | users, facilities, departments, service profiles, staff, account status |

Errors share one shape: `{ "error": { "code", "message", "details" } }`.

## Security notes

- Access tokens are short lived (15 minutes); refresh tokens rotate on every use and are
  revoked on logout, password change or account deactivation.
- Roles are enforced per route: `citizen` for their own tokens, `staff` for their assigned
  departments, `admin` for platform-wide management.
- Helmet, CORS allow-listing, a global rate limit plus a stricter auth limiter, and
  `trust proxy` behind Nginx.
- Passwords are bcrypt hashed; refresh tokens are stored hashed.
- Secrets live in `.env` (git-ignored), Kubernetes secrets, or GitHub Actions secrets.

## Development

```bash
cd backend && npm install && npm run dev     # :5000, node --watch
cd dashboard && npm install && npm run dev   # :5173, proxies /api to :5000
cd mobile && npm install && npx expo start
cd ai_service && pip install -r requirements.txt && python scripts/train_model.py
```

Checks, which CI runs on every push:

```bash
cd backend && npm run lint && npm test        # node:test
cd dashboard && npm run lint && npm run build
cd ai_service && ruff check app tests scripts && pytest
```

Lockfiles are not committed yet, so CI falls back to `npm install`. Run an install once
per JavaScript package and commit the generated `package-lock.json` to switch to `npm ci`.

The Expo placeholder icons in `mobile/assets/` are generated by
`node mobile/scripts/generate-placeholder-assets.js`. Replace them with real artwork before
shipping. FCM additionally needs `mobile/assets/google-services.json`; see
[DEPLOY.md](DEPLOY.md#8-firebase-cloud-messaging).

## CI/CD

| Workflow | Trigger | Does |
|---|---|---|
| `.github/workflows/ci.yml` | push, pull request | Backend lint/test, AI lint/test/train smoke, dashboard lint/build, dependency audits |
| `.github/workflows/docker-build.yml` | tags, manual | Builds and pushes API, AI and dashboard images |
| `.github/workflows/deploy.yml` | tags, manual | SSH deploy to a Cloud VM: migrate, roll, health check, rollback |

`infra/k8s/` holds a Kubernetes deployment for the API and AI service with liveness and
readiness probes wired to `/health` and `/health/ready`.

## License

MIT