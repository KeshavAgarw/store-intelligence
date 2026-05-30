FROM python:3.11-slim

WORKDIR /app

COPY requirements-docker.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY scripts ./scripts

ENV DATABASE_URL=sqlite:///./data/store.db
ENV DATA_DIR=/app/data
ENV METRICS_REFERENCE_DATE=2026-03-03T12:00:00Z

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
