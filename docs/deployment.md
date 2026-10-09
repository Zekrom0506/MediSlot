# Deploying MediSlot on one AWS EC2 server

This runs the whole stack with Docker Compose on a single server, with Nginx on
the host handling HTTPS. It is the simplest real deployment, not a highly
available one (see "Limits" at the end).

## 1. Create the server

- AMI: Ubuntu Server 24.04 LTS
- Instance type: `t3.medium` (2 vCPU, 4 GB) or larger
- Storage: 30 GB gp3
- Security group inbound rules:
  - 22 (SSH) from your own IP only
  - 80 (HTTP) and 443 (HTTPS) from anywhere
- Allocate an Elastic IP and attach it, so the address survives restarts.
- In your DNS provider, add an `A` record such as `medislot.example.com` pointing to the Elastic IP.

## 2. Install Docker and Nginx

```bash
ssh ubuntu@<elastic-ip>

sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo apt install -y nginx certbot python3-certbot-nginx git
exit   # log out and back in so the docker group applies
```

## 3. Copy the project

```bash
ssh ubuntu@<elastic-ip>
git clone https://github.com/<your-username>/medislot.git
cd medislot
```

## 4. Set the environment variables

```bash
cp .env.example .env
nano .env
```

Change at least:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` (the API refuses to start with the default JWT secret) |
| `POSTGRES_PASSWORD` | a long random password, also used inside `DATABASE_URL` |
| `JWT_SECRET_KEY` | output of `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GRAFANA_ADMIN_PASSWORD` | a strong password |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS` | your email provider, e.g. Amazon SES SMTP |

`chmod 600 .env` so only your user can read it.

## 5. Start the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec api python -m app.seed      # optional: demo data
curl http://127.0.0.1:3000/api/doctors/filters   # quick check
```

The API container runs `alembic upgrade head` on every start, so new migrations
are applied automatically when you deploy a new version.

## 6. Put Nginx and HTTPS in front

```bash
sudo cp deploy/nginx-medislot.conf /etc/nginx/sites-available/medislot
sudo sed -i 's/medislot.example.com/<your-domain>/' /etc/nginx/sites-available/medislot
sudo ln -s /etc/nginx/sites-available/medislot /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d <your-domain> --redirect -m you@example.com --agree-tos
```

Certbot gets a free Let's Encrypt certificate, adds the HTTPS server block,
redirects HTTP to HTTPS and installs a timer that renews the certificate.
Check renewal with `sudo certbot renew --dry-run`.

## 7. Deploying a new version

```bash
cd ~/medislot
git pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

## 8. Backups

A nightly database dump to S3 is enough to start with:

```bash
# crontab -e
0 2 * * * cd ~/medislot && docker compose exec -T postgres pg_dump -U medislot medislot | gzip > ~/backup.sql.gz && aws s3 cp ~/backup.sql.gz s3://<bucket>/medislot/$(date +\%F).sql.gz
```

## Limits of this setup

Everything is on one machine, so a server failure means downtime and the
database lives on its disk. The next steps would be a managed database
(Amazon RDS with automated backups), managed Redis (ElastiCache), and running
the API on two or more instances behind a load balancer.
