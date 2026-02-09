FROM python:3.14.3-alpine

LABEL maintainer="Mortell560"
LABEL description="A simple grade checker for students at polytech to check their grades on the go."

ENV PYTHONUNBUFFERED=1
ENV OASIS_USERNAME=""
ENV OASIS_PASSWORD=""
ENV OASIS_BASE_URL="https://polytech-saclay.oasis.aouka.org/"
ENV DATABASE_PATH="/app/database.db"

WORKDIR /app

COPY requirements.txt .
COPY README.md .
COPY LICENSE .

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY ./src /app/src

WORKDIR /app/src
