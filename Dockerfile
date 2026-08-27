# Pin to a specific image digest for supply-chain security.
# Find the latest digest at https://hub.docker.com/_/python/tags
FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    SEMGREP_SEND_METRICS=off \
    SEMGREP_LOG_FILE=/tmp/aegispr-semgrep.log

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && useradd --create-home --uid 1001 aegispr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY src /app/src
COPY aegispr_action.py /app/aegispr_action.py

USER aegispr
ENTRYPOINT ["python", "/app/aegispr_action.py"]
