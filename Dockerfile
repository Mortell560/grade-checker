FROM python:3.14.3-alpine

LABEL maintainer="Mortell560"
LABEL description="A simple grade checker for students at polytech to check their grades on the go."

ENV PYTHONUNBUFFERED=1
ENV OASIS_LOGIN=""
ENV OASIS_PASSWORD=""
ENV OASIS_BASE_URL="https://polytech-saclay.oasis.aouka.org"
ENV DB_PATH="/app/database.db"
ENV WEBHOOK_URL=""
ENV SYNC_INTERVAL_SECONDS=3600

WORKDIR /app

COPY requirements.txt .
COPY README.md .
COPY LICENSE .

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY ./src /app/src

WORKDIR /app/src

ENTRYPOINT ["python", "main.py"]