FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Config, the SQLite DB, the model registry and datasets all resolve relative to the
# working directory, so the app must run from /app.
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY training ./training
COPY experiments ./experiments
COPY data/benchmarks ./data/benchmarks

RUN useradd --create-home appuser && mkdir -p /app/state /app/data/processed /app/experiments/reports /app/models && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
