# Gateway API and MQTT ingestion.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY gateway /app/gateway
COPY shared /app/shared

CMD ["python", "-m", "uvicorn", "gateway.application:app", "--host", "0.0.0.0", "--port", "8000"]