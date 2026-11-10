FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY requirements.lock /app/requirements.lock
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

RUN pip install --require-hashes -r requirements.lock && pip install --no-deps .
RUN addgroup --system app && adduser --system --ingroup app --home /app app && chown -R app:app /app

USER app

CMD ["python", "-m", "app.run_api"]
