# Facility simulation, device publishers, and development attacks.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY simulator /app/simulator
COPY shared /app/shared

CMD ["python", "-m", "uvicorn", "simulator.facility:app", "--host", "0.0.0.0", "--port", "8001"]
