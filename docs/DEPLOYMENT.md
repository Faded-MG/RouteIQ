# DEPLOYMENT.md — FuelRoute

Targets: local development (P1), CI (P1), single Linux VPS with Docker Compose, Nginx, HTTPS (P2). Commands assume Ubuntu 24.04 LTS on the VPS; replace `example.com`, `OWNER`, `deploy` where marked. Everything here must be executed and verified by the implementer (AGENTS.md §9); nothing was run while writing this blueprint.

## 1. Development environment

Prerequisites: Docker ≥ 26 with Compose v2, Python 3.13 (confirm against the pinned Django's supported list), Node 22 LTS, Git.

```bash
git clone git@github.com:OWNER/fuelroute.git && cd fuelroute
cp .env.example .env                       # then edit values; never commit .env
docker compose --env-file .env -f deploy/docker-compose.yml up -d db

python3.13 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements/dev.txt
cd backend
# Host-run Django connects to localhost:5433 (mapped from container port 5432 via DB_HOST_PORT to avoid conflicts)
python manage.py migrate
python manage.py createcachetable
python manage.py import_stations --csv ../data/fuel-prices-for-be-assessment.csv
python manage.py runserver 0.0.0.0:8000
# in another shell
cd frontend && npm ci && npm run dev        # http://localhost:5173 proxies /api to :8000
```

Everything in containers instead: `docker compose --env-file .env -f deploy/docker-compose.yml up --build` (services `db`, `web`), then run the three management commands via `docker compose --env-file .env -f deploy/docker-compose.yml exec web python manage.py …`. (`--env-file` is required because Compose reads variable substitutions from the directory of the compose file, `deploy/`, not from the repository root.)

## 2. Environment variables

Defined once in `.env.example` (dummy values), read by Django settings and Compose.

| Variable | Example | Required | Meaning |
|---|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` | yes | `dev`, `prod`, `test`. |
| `DJANGO_SECRET_KEY` | 50+ random chars | prod | `python -c "import secrets;print(secrets.token_urlsafe(64))"`. |
| `DJANGO_DEBUG` | `0` | no | Must be `0` in prod (`check --deploy` enforces). |
| `DJANGO_ALLOWED_HOSTS` | `example.com` | prod | Comma-separated. |
| `CORS_ALLOWED_ORIGINS` | `https://example.com` | no | Empty = same-origin only. |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `fuelroute` / `fuelroute` / random | yes | DB credentials. |
| `POSTGRES_HOST` / `POSTGRES_PORT` / `DB_HOST_PORT` | `localhost` / `5433` / `5433` | yes | Host-run dev uses `localhost:5433` (mapped via `DB_HOST_PORT` to avoid host 5432 conflict); container web uses `db:5432`. |
| `OSRM_BASE_URL` | `https://router.project-osrm.org` | no | Swap for self-hosted (`http://osrm:5000`). |
| `NOMINATIM_BASE_URL` | `https://nominatim.openstreetmap.org` | no | |
| `OPEN_METEO_BASE_URL` | `https://api.open-meteo.com` | no | |
| `ENABLE_WEATHER` | `1` | no | `0` disables the weather call entirely. |
| `APP_CONTACT` | `https://github.com/OWNER/fuelroute` | **yes** | Placed in the outbound `User-Agent`. Use a repo URL or a project mailbox; never a personal address by default. |
| `PLAN_RATE_LIMIT` | `30/min` | no | Inbound throttle. |
| `GUNICORN_WORKERS` | `3` | no | 2–3 for a 2-vCPU VPS. |
| `LOG_LEVEL` | `INFO` | no | |
| `IMAGE_TAG` | `v1.0.0` | prod | Image tag used by Compose. |
| `GHCR_OWNER` | `owner` (lowercase) | prod | Registry namespace. |
| `DOMAIN` | `example.com` | prod | Used by Nginx and certbot scripts. |
| `VITE_API_BASE_URL`, `VITE_MAP_STYLE_URL` | `/api/v1`, `https://tiles.openfreemap.org/styles/positron` | build args | Frontend; MapLibre loads the OpenFreeMap vector style, with attribution handled by the library. |

## 3. Dockerfiles

### `backend/Dockerfile`
```dockerfile
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN useradd --system --uid 10001 --create-home app
COPY requirements/base.txt requirements/base.txt
RUN pip install -r requirements/base.txt
COPY --chown=app:app . .
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live',timeout=2).status==200 else 1)"
CMD ["sh","-c","gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout 30 --access-logfile - --error-logfile -"]
```
`psycopg[binary]` and `numpy` ship wheels for slim images, so no compiler is installed. If the pinned versions lack a wheel, add `build-essential libpq-dev` in a builder stage (report as a deviation).

### `frontend/Dockerfile`
```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_MAP_STYLE_URL=https://tiles.openfreemap.org/styles/positron
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```
`frontend/nginx.conf` (standalone/dev image): SPA fallback `try_files $uri /index.html;` and `location /api/ { proxy_pass http://web:8000; }`. In production the file in `deploy/nginx/fuelroute.conf` is mounted over `/etc/nginx/conf.d/default.conf` (§6).

## 4. Docker Compose architecture

```mermaid
flowchart TB
  Internet --> nginx[nginx (frontend image) :80/:443]
  nginx -->|/api/*| web[web: gunicorn :8000]
  nginx -->|/| static[(static dist inside image)]
  web --> db[(db: postgres:17-alpine)]
  certbot[certbot] -.shared volumes.- nginx
  backup[backup cron on host] --> db
```

### `deploy/docker-compose.yml` (development)
```yaml
name: fuelroute-dev
services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-fuelroute}
      POSTGRES_USER: ${POSTGRES_USER:-fuelroute}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-fuelroute}
    ports: ["127.0.0.1:${DB_HOST_PORT:-5433}:5432"]
    volumes: [dbdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 10
  web:
    build: ../backend
    env_file: ../.env
    environment: { POSTGRES_HOST: db, POSTGRES_PORT: 5432, DJANGO_SETTINGS_MODULE: config.settings.dev }
    depends_on: { db: { condition: service_healthy } }
    ports: ["127.0.0.1:8000:8000"]
volumes:
  dbdata:
```

### `deploy/docker-compose.prod.yml`
```yaml
name: fuelroute
services:
  db:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    command: ["postgres","-c","max_connections=50","-c","shared_buffers=128MB",
              "-c","effective_cache_size=384MB","-c","work_mem=4MB","-c","log_min_duration_statement=500"]
    volumes: [dbdata:/var/lib/postgresql/data]
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 3s
      retries: 10
  web:
    image: ghcr.io/${GHCR_OWNER}/fuelroute-backend:${IMAGE_TAG}
    restart: unless-stopped
    env_file: ../.env
    environment: { POSTGRES_HOST: db, DJANGO_SETTINGS_MODULE: config.settings.prod }
    depends_on: { db: { condition: service_healthy } }
    networks: [internal]
    mem_limit: 768m
    read_only: true
    tmpfs: [/tmp]
  nginx:
    image: ghcr.io/${GHCR_OWNER}/fuelroute-frontend:${IMAGE_TAG}
    restart: unless-stopped
    depends_on: [web]
    ports: ["80:80","443:443"]
    volumes:
      - ./nginx/fuelroute.conf:/etc/nginx/conf.d/default.conf:ro
      - certs:/etc/letsencrypt:ro
      - acme:/var/www/certbot:ro
    networks: [internal]
    healthcheck:
      test: ["CMD","wget","-qO-","http://127.0.0.1/healthz"]
      interval: 15s
      timeout: 3s
      retries: 5
  certbot:
    image: certbot/certbot
    profiles: ["tools"]
    volumes: [certs:/etc/letsencrypt, acme:/var/www/certbot]
networks:
  internal: {}
volumes:
  dbdata:
  certs:
  acme:
```
The `web` service is not published to the host; only Nginx is. The DB has no published port.

## 5. PostgreSQL configuration

* Image `postgres:17-alpine`; data in the named volume `dbdata`.
* Settings above suit a 2 vCPU / 2 GB VPS. Re-tune if the VPS differs (`shared_buffers ≈ 25% RAM`).
* Application role = the Compose user (single-tenant). For production hardening (P3) create a separate migration role.
* Connections: 3 Gunicorn workers × 1 connection each (`CONN_MAX_AGE=60`) → ≪ `max_connections`.
* Required one-time commands after first start: `migrate`, `createcachetable`, `import_stations` (§9).

## 6. Nginx (`deploy/nginx/fuelroute.conf`)

```nginx
# Rate-limit zone must live in http{}; conf.d files are included in http{}.
limit_req_zone $binary_remote_addr zone=plan:10m rate=30r/m;

server {
  listen 80;
  server_name example.com;                      # replace
  location /.well-known/acme-challenge/ { root /var/www/certbot; }
  location /healthz { access_log off; return 200 "ok\n"; }
  location / { return 301 https://$host$request_uri; }
}

server {
  listen 443 ssl;
  http2 on;
  server_name example.com;                      # replace
  ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_session_cache shared:SSL:10m;

  add_header Strict-Transport-Security "max-age=31536000" always;
  add_header X-Content-Type-Options nosniff always;
  add_header X-Frame-Options DENY always;
  add_header Referrer-Policy strict-origin-when-cross-origin always;
  # CSP allows the MapLibre style and worker requests; adjust if VITE_MAP_STYLE_URL changes.
  add_header Content-Security-Policy "default-src 'self'; worker-src 'self' blob:; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' https://tiles.openfreemap.org; connect-src 'self' https://tiles.openfreemap.org" always;

  client_max_body_size 8k;
  gzip on; gzip_types application/json text/css application/javascript image/svg+xml;

  location /api/ {
    limit_req zone=plan burst=10 nodelay;
    proxy_pass http://web:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Request-ID $request_id;
    proxy_read_timeout 35s;
  }
  location /healthz { access_log off; return 200 "ok\n"; }
  location /assets/ { root /usr/share/nginx/html; expires 1y; add_header Cache-Control "public, immutable"; }
  location / { root /usr/share/nginx/html; try_files $uri /index.html; add_header Cache-Control "no-cache"; }
}
```
Django must set `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` and read `X-Request-ID`. Validate with `docker run --rm -v $PWD/deploy/nginx/fuelroute.conf:/etc/nginx/conf.d/default.conf:ro ghcr.io/OWNER/fuelroute-frontend:TAG nginx -t` (certificate paths must exist for the test; CI creates a throw-away self-signed pair).

## 7. VPS provisioning (once)

```bash
# as root on a fresh Ubuntu 24.04 VPS
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh && cp ~/.ssh/authorized_keys /home/deploy/.ssh/ && chown -R deploy:deploy /home/deploy/.ssh
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/; s/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart ssh

apt-get update && apt-get -y upgrade
apt-get -y install ufw fail2ban unattended-upgrades ca-certificates curl
ufw default deny incoming && ufw default allow outgoing
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable

# Docker Engine (official convenience repo method; verify at https://docs.docker.com/engine/install/ubuntu/ before running)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update && apt-get -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
usermod -aG docker deploy
```
Then as `deploy`: `git clone https://github.com/OWNER/fuelroute.git ~/fuelroute`, `cd ~/fuelroute`, `cp .env.example .env`, edit `.env` (strong secrets, `DOMAIN`, `IMAGE_TAG`, `GHCR_OWNER`, `APP_CONTACT`), `chmod 600 .env`. Point the domain's A record to the VPS IP before §9. Add a swap file (2 GB) if the VPS has ≤ 2 GB RAM.

## 8. GitHub Actions

### `.github/workflows/ci.yml`
```yaml
name: ci
on:
  push: { branches: [main] }
  pull_request:
jobs:
  backend:
    runs-on: ubuntu-24.04
    services:
      postgres:
        image: postgres:17-alpine
        env: { POSTGRES_DB: fuelroute, POSTGRES_USER: fuelroute, POSTGRES_PASSWORD: fuelroute }
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U fuelroute" --health-interval 5s --health-timeout 3s --health-retries 10
    env:
      DJANGO_SETTINGS_MODULE: config.settings.test
      POSTGRES_DB: fuelroute
      POSTGRES_USER: fuelroute
      POSTGRES_PASSWORD: fuelroute
      POSTGRES_HOST: localhost
      DJANGO_SECRET_KEY: ci-only-not-a-secret
      APP_CONTACT: https://github.com/${{ github.repository }}
    defaults: { run: { working-directory: backend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.13", cache: pip, cache-dependency-path: backend/requirements/dev.txt }
      - run: pip install -r requirements/dev.txt
      - run: ruff check . && ruff format --check .
      - run: python manage.py makemigrations --check --dry-run
      - run: pytest -m "not perf" --cov=apps --cov-report=xml --cov-fail-under=85
      - run: pip-audit -r requirements/base.txt
  frontend:
    runs-on: ubuntu-24.04
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci
      - run: npm run lint && npm run typecheck
      - run: npm run test:coverage
      - run: npm run build
      - run: npm audit --omit=dev --audit-level=high
  docker:
    runs-on: ubuntu-24.04
    needs: [backend, frontend]
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t fuelroute-backend:ci backend
      - run: docker build -t fuelroute-frontend:ci frontend
      - run: cp .env.example .env
      - run: docker compose --env-file .env -f deploy/docker-compose.prod.yml config > /dev/null
```
Action major versions above (`checkout@v4`, `setup-python@v5`, `setup-node@v4`) are the ones known at writing time; the implementer confirms the current majors on the Marketplace and pins accordingly (report as a note if they differ).

### `.github/workflows/deploy.yml`
```yaml
name: deploy
on:
  push: { tags: ["v*"] }
permissions: { contents: read, packages: write }
jobs:
  publish:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with: { registry: ghcr.io, username: "${{ github.actor }}", password: "${{ secrets.GITHUB_TOKEN }}" }
      - uses: docker/setup-buildx-action@v3
      - id: owner
        run: echo "lower=$(echo '${{ github.repository_owner }}' | tr '[:upper:]' '[:lower:]')" >> "$GITHUB_OUTPUT"
      - uses: docker/build-push-action@v6
        with:
          context: backend
          push: true
          tags: ghcr.io/${{ steps.owner.outputs.lower }}/fuelroute-backend:${{ github.ref_name }}
      - uses: docker/build-push-action@v6
        with:
          context: frontend
          push: true
          tags: ghcr.io/${{ steps.owner.outputs.lower }}/fuelroute-frontend:${{ github.ref_name }}
  release:
    needs: publish
    runs-on: ubuntu-24.04
    environment: production
    steps:
      - name: Deploy over SSH
        env:
          SSH_KEY: ${{ secrets.VPS_SSH_KEY }}
          HOST: ${{ secrets.VPS_HOST }}
          KNOWN_HOSTS: ${{ secrets.VPS_KNOWN_HOSTS }}
          TAG: ${{ github.ref_name }}
        run: |
          install -m 700 -d ~/.ssh
          printf '%s\n' "$SSH_KEY" > ~/.ssh/id_deploy && chmod 600 ~/.ssh/id_deploy
          printf '%s\n' "$KNOWN_HOSTS" > ~/.ssh/known_hosts
          ssh -i ~/.ssh/id_deploy "deploy@${HOST}" "cd ~/fuelroute && ./deploy/scripts/deploy.sh ${TAG}"
      - name: Smoke test
        run: curl -fsS "https://${{ secrets.DOMAIN }}/api/v1/health/ready"
```
Secrets to create: `VPS_SSH_KEY` (dedicated deploy key, no passphrase), `VPS_HOST`, `VPS_KNOWN_HOSTS` (`ssh-keyscan -H host`), `DOMAIN`. The VPS pulls from GHCR: run once `echo <PAT with read:packages> | docker login ghcr.io -u OWNER --password-stdin` as `deploy`, or make the packages public.

## 9. First deployment, HTTPS, migrations

`deploy/scripts/init-letsencrypt.sh` (run once, as `deploy`, after DNS resolves):
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ../.env
DC="docker compose --env-file ../.env -f docker-compose.prod.yml"
EMAIL="${LETSENCRYPT_EMAIL:?set LETSENCRYPT_EMAIL in .env}"
# 1) temporary self-signed cert so nginx can start
# (if `openssl` is missing in the certbot image, prefix the command with: apk add --no-cache openssl &&   -- certbot image is Alpine-based, verify)
$DC run --rm --entrypoint sh certbot -c \
  "mkdir -p /etc/letsencrypt/live/${DOMAIN} && openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
   -keyout /etc/letsencrypt/live/${DOMAIN}/privkey.pem -out /etc/letsencrypt/live/${DOMAIN}/fullchain.pem -subj /CN=localhost"
$DC up -d db web nginx
# 2) real certificate via webroot
$DC run --rm --entrypoint sh certbot -c \
  "rm -rf /etc/letsencrypt/live/${DOMAIN} /etc/letsencrypt/archive/${DOMAIN} /etc/letsencrypt/renewal/${DOMAIN}.conf"
$DC run --rm certbot certonly --webroot -w /var/www/certbot \
  -d "${DOMAIN}" --email "${EMAIL}" --agree-tos --no-eff-email
$DC exec nginx nginx -s reload
```
`LETSENCRYPT_EMAIL` is added to `.env.example` (documented there as "contact for Let's Encrypt expiry notices").
Renewal (host cron for `deploy`, twice daily): `0 3,15 * * * cd ~/fuelroute/deploy && docker compose --env-file ../.env -f docker-compose.prod.yml run --rm certbot renew --quiet && docker compose --env-file ../.env -f docker-compose.prod.yml exec -T nginx nginx -s reload`.

`deploy/scripts/deploy.sh <tag>`:
```bash
#!/usr/bin/env bash
set -euo pipefail
TAG="${1:?usage: deploy.sh <tag>}"
cd "$(dirname "$0")/.."                                          # deploy/
git fetch --tags --quiet && git checkout --quiet "$TAG"          # keeps compose/nginx files in step with the image tag
grep -q '^IMAGE_TAG=' ../.env && sed -i "s/^IMAGE_TAG=.*/IMAGE_TAG=${TAG}/" ../.env || echo "IMAGE_TAG=${TAG}" >> ../.env
source ../.env
DC="docker compose --env-file ../.env -f docker-compose.prod.yml"
./scripts/backup.sh || echo "no database yet, skipping pre-deploy backup"   # §12
echo "${TAG}" >> ../.deployed_tags                               # history for rollback.sh (git-ignored)
$DC pull
$DC up -d db
$DC run --rm web python manage.py migrate --noinput
$DC run --rm web python manage.py createcachetable
$DC run --rm web python manage.py check --deploy
$DC run --rm -v "$PWD/../data:/data:ro" web \
  python manage.py import_stations --csv /data/fuel-prices-for-be-assessment.csv   # idempotent
$DC up -d --remove-orphans web nginx
for i in $(seq 1 30); do
  if $DC exec -T web python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready',timeout=2).status==200 else 1)" >/dev/null 2>&1; then
    echo "healthy"; exit 0
  fi
  sleep 2
done
echo "health check failed" >&2; exit 1
```
Note: `import_stations` ships in the image only if `apps/stations/data/*.csv` are copied into it (they are inside `backend/`); the CSV itself is mounted from the repo clone.

Migration policy: migrations must be backward compatible with the previous release (add nullable/default columns first, remove in a later release) so a code rollback does not require a DB rollback.

## 10. Health checks

| Check | Endpoint / command | Used by |
|---|---|---|
| Liveness | `GET /api/v1/health/live` | Docker `HEALTHCHECK`, uptime monitor |
| Readiness | `GET /api/v1/health/ready` (DB + station count) | `deploy.sh`, CI smoke |
| Nginx | `GET /healthz` | Compose healthcheck |
| Postgres | `pg_isready` | Compose healthcheck |
| Certificate expiry | `echo | openssl s_client -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -enddate` | monthly manual / cron alert |

An external uptime monitor (free tier of any provider) on `/api/v1/health/ready` is recommended (P2).

## 11. Logging

* Django/Gunicorn log JSON to stdout/stderr; Nginx logs to stdout. Compose uses the `json-file` driver with rotation: add to every service `logging: { driver: json-file, options: { max-size: "10m", max-file: "5" } }`.
* Read logs (from `deploy/`): `docker compose --env-file ../.env -f docker-compose.prod.yml logs -f --since 30m web`.
* Fields: ARCHITECTURE §10. Alert-worthy patterns: `"level":"ERROR"`, `UPSTREAM_` codes > 5/min, `status":5` rates.

## 12. Backups

`deploy/scripts/backup.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source ../.env
mkdir -p ~/backups
OUT=~/backups/fuelroute_$(date -u +%Y%m%dT%H%M%SZ).dump
docker compose --env-file ../.env -f docker-compose.prod.yml exec -T db pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$OUT"
find ~/backups -name 'fuelroute_*.dump' -mtime +14 -delete
echo "$OUT"
```
Cron (user `deploy`): `15 2 * * * ~/fuelroute/deploy/scripts/backup.sh >> ~/backups/backup.log 2>&1`. Copy dumps off the VPS (e.g., `rclone`/`scp` to another host) — a same-disk backup is not a backup. The caches and `Station` data are reproducible (`import_stations`), so the real irreplaceable state is small; the backup mainly protects configuration continuity.
Restore test (do once, record the date; run from `~/fuelroute/deploy`, prefix every command with `docker compose --env-file ../.env`):
```bash
docker compose -f docker-compose.prod.yml exec -T db createdb -U "$POSTGRES_USER" restore_test
docker compose -f docker-compose.prod.yml exec -T db pg_restore -U "$POSTGRES_USER" -d restore_test --no-owner < ~/backups/<file>.dump
docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -d restore_test -c "select count(*) from stations_station;"
docker compose -f docker-compose.prod.yml exec -T db dropdb -U "$POSTGRES_USER" restore_test
```

## 13. Rollback

`deploy/scripts/rollback.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
PREV=$(tail -n 2 .deployed_tags | head -n 1)
[ -n "$PREV" ] || { echo "no previous tag"; exit 1; }
echo "rolling back to $PREV"
./deploy/scripts/deploy.sh "$PREV"
```
* Code-only rollback (normal case): above; images for the previous tag are still in GHCR.
* If a release applied a destructive migration (should not happen under the migration policy): stop `web`, restore the pre-deploy dump taken by `deploy.sh` (§12 restore commands into the real DB after `dropdb`/`createdb`), then deploy the previous tag.
* Verify after any rollback: `curl -fsS https://$DOMAIN/api/v1/health/ready` and one plan request.

## 14. Release checklist

1. CI green on `main`; tag `vX.Y.Z`; `git push origin vX.Y.Z`.
2. Watch the `deploy` workflow; confirm smoke step passes.
3. `curl -sS https://$DOMAIN/api/v1/config` shows `station_count: 6626`.
4. One manual plan request (coordinates only, to avoid geocoder load).
5. Record the tag in the project log.
