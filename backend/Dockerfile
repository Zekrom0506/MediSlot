FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# --proxy-headers makes request.client.host the real visitor IP behind Nginx,
# which the per-IP login rate limit depends on. Only proxies inside the Docker
# network are trusted (uvicorn reads FORWARDED_ALLOW_IPS): uvicorn then takes the
# right-most address that is not one of our own proxies, so an X-Forwarded-For
# header made up by the visitor is ignored. Never use "*" here: it trusts the
# left-most address, which the visitor controls.
ENV FORWARDED_ALLOW_IPS=172.16.0.0/12
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
