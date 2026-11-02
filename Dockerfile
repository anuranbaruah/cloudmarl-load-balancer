# One image for all Python services (worker, balancer, cloud); compose picks the command.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.0 "uvicorn[standard]==0.30.6" \
    "psycopg[binary]==3.2.3" httpx==0.27.2
COPY worker/ worker/
COPY balancer/ balancer/
COPY cloud/ cloud/
