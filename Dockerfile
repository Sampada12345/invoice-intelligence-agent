FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md alembic.ini /app/
COPY src /app/src
COPY deploy /app/deploy
COPY .streamlit /app/.streamlit

RUN pip install --upgrade pip && pip install .

RUN useradd --system --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/secrets \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8080 8501

CMD ["python", "-m", "invoice_agent.runtime.agent_service"]
