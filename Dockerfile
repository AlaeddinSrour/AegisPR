# NOTE: For maximum supply-chain security, pin to a specific image digest:
#   FROM python:3.11-slim@sha256:<digest>
# You can find the latest digest at https://hub.docker.com/_/python/tags
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src

USER nobody
ENTRYPOINT ["python", "-m", "src.main"]
