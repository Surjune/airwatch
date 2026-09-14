# Deploying AirWatch on AWS

One EC2 server in Mumbai runs the whole stack with Docker Compose: Caddy (HTTPS
and the web app), the API, the hourly worker and TimescaleDB with PostGIS. It
costs roughly **US$20 a month**, which AWS credits cover during an evaluation.

Nothing here needs AWS access keys on anyone's laptop: you click through the
console, SSH in, and run two scripts.

---

## 0. Protect the account first (5 minutes)

1. **Root account MFA** — top-right account menu → *Security credentials* →
   *Assign MFA device*.
2. **Budget alarm** — *Billing and Cost Management* → *Budgets* → *Create budget*
   → *Monthly cost budget*, amount **US$25**, alerts at 50 %, 80 % and 100 % to
   your email.
3. Check your credits and their expiry under *Billing* → *Credits*.

## 1. Launch the server (5 minutes)

Console → region **Asia Pacific (Mumbai) ap-south-1** (top-right) → **EC2** →
**Launch instance**:

| Setting | Value |
|---|---|
| Name | `airwatch` |
| Image | **Ubuntu Server 24.04 LTS**, 64-bit (x86) |
| Instance type | **t3.small** (2 vCPU, 2 GB) — not a micro: the database, API and worker together need 2 GB |
| Key pair | *Create new key pair* → `airwatch-key`, type ED25519, format `.pem`. Keep the file safe. |
| Network → Security group | *Create security group* with three inbound rules: **SSH 22 from My IP**, **HTTP 80 from Anywhere**, **HTTPS 443 from Anywhere** |
| Storage | **30 GiB gp3** |

Launch. Then **Elastic IPs** (left menu) → *Allocate* → select it → *Associate* with
the `airwatch` instance, so the address survives restarts.

## 2. Point a domain at it (5 minutes)

Either a domain you own — add an **A record** to the Elastic IP — or a free
[DuckDNS](https://www.duckdns.org) subdomain pointed at the Elastic IP. Caddy needs
the name to resolve before it can obtain the HTTPS certificate.

## 3. Install and configure (10 minutes)

From your computer (Windows PowerShell works):

```bash
ssh -i airwatch-key.pem ubuntu@<ELASTIC-IP>
```

On the server:

```bash
curl -fsSL https://raw.githubusercontent.com/Surjune/airwatch/main/infra/deploy/bootstrap.sh -o bootstrap.sh
```

```bash
bash bootstrap.sh
```

It installs Docker, adds swap, enables automatic security updates, clones the
repository and creates `~/airwatch/.env`. Fill that file in:

```bash
nano ~/airwatch/.env
```

- `SITE_ADDRESS` and `CORS_ALLOWED_ORIGINS` — your domain (the latter with `https://`).
- `POSTGRES_PASSWORD` — paste the output of `openssl rand -hex 24`.
- `OPERATOR_API_KEY` — paste the output of `openssl rand -hex 32`, and keep a copy:
  operators sign in to the authority console with it.
- Your OpenAQ, data.gov.in and FIRMS keys.
- `GEMINI_API_KEY` — from https://aistudio.google.com. Reads residents' photos and writes alert
  briefs; without it both are skipped with a stated reason.
- `SARVAM_API_KEY` (optional) — voices the spoken guide in English, Hindi and Tamil. `deploy.sh`
  generates every paragraph once after it starts the stack; without a key the guide is text only.
- Earth Engine (optional): the service-account email and project id. Then copy the
  key file from **your computer**:

```bash
scp -i airwatch-key.pem gee-key.json ubuntu@<ELASTIC-IP>:~/airwatch/secrets/gee-key.json
```

`deploy.sh` hands `secrets/` to the container user (uid 10001), so the key is
readable inside the API and worker but by no other account on the server.

Log out and back in once, so Docker works without `sudo`.

## 4. Deploy and load data (20–40 minutes, mostly waiting)

```bash
bash ~/airwatch/infra/deploy/deploy.sh --first-load
```

This builds the images, runs migrations, seeds the authority and source
registries, starts everything, backfills 14 days of PM2.5 and PM10 for Delhi,
Kanpur and Coimbatore, fetches the official AQI and satellite data, and finishes by
replaying the recorded Anand Vihar episode — which must print `PASS`.

Open `https://<your-domain>`. The worker now runs every hour on its own.

## 5. Backups

```bash
(crontab -l 2>/dev/null; echo "30 20 * * * bash $HOME/airwatch/infra/deploy/backup.sh >> $HOME/airwatch/backups/backup.log 2>&1") | crontab -
```

That keeps 14 nightly database dumps on the server. For copies that survive the
server, also enable EBS snapshots: *EC2* → *Lifecycle Manager* → policy for the
instance's volume, daily, keep 7.

## Day-to-day

| Task | Command (on the server) |
|---|---|
| Deploy the latest `main` | `bash ~/airwatch/infra/deploy/deploy.sh` |
| See what is running | `docker compose -f ~/airwatch/infra/docker-compose.prod.yml --env-file ~/airwatch/.env ps` |
| Worker log | `docker compose -f ~/airwatch/infra/docker-compose.prod.yml --env-file ~/airwatch/.env logs -f worker` |
| API log | same, with `api` |

Uptime: add a free monitor (for example UptimeRobot) on
`https://<your-domain>/v1/health`.

## When the credits run out

Everything is containers and one `.env`, so the stack moves unchanged to any
Ubuntu server — including Oracle Cloud's Always Free tier. Restore the latest
backup there, point the DNS record at the new address, and run `deploy.sh`.
Stop or terminate the EC2 instance and release the Elastic IP afterwards, or both
keep billing.
