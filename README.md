# OT-SOAR Gateway

A proof-of-concept gateway for managing simulated IoT/OT devices in a data-center setting. It combines personnel and device registration, ABAC access rules, telemetry monitoring, device-behaviour policies, event logging, and automated responses to selected threat scenarios.

The repository contains three running applications: a FastAPI gateway, a FastAPI facility simulator, and a React dashboard. Mosquitto carries MQTT telemetry. The gateway stores its records in SQLite. Docker Compose starts all four services.

## Requirements

- Docker Engine with the Docker Compose plugin
- Ports `5173`, `8000`, `8001`, and `1883` available on the host

No Python virtual environment or dashboard `node_modules` directory is required to run the Compose setup; each service installs its own dependencies in its image.

## Build and run

From the repository root:

```bash
docker compose up --build
```

The first build downloads the base images and installs the Python and JavaScript dependencies. Once the services start, open:

- Dashboard: <http://localhost:5173>
- Gateway API and interactive API documentation: <http://localhost:8000/docs>
- Facility simulator API: <http://localhost:8001/docs>
- Gateway health: <http://localhost:8000/health>

The gateway database is stored in a named Docker volume and is kept when containers stop. To remove that database and start from a clean installation, run `docker compose down -v`.

## Demo reset

The dashboard's Simulation page has a **Reset to seeded state** button. It clears demonstration records and restores the predefined rooms, devices, personnel, and policies. The API equivalent is:

```bash
curl -X POST http://localhost:8000/system/reset-demo-data
```

Reset is provided for repeatable demonstration and evaluation. It deletes runtime data in the project database.

## Run the evaluation

Start the Compose stack first, then install the evaluation client and run the Python suite from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r evaluation/requirements.txt
pytest evaluation/
```

The evaluation suite talks to the running services, so those containers must remain up while it runs. It resets the demonstration state between scenarios and appends its results to `evaluation/results/test_results.csv` and `evaluation/results/test_results.jsonl`. Suite 10 also appends measurements to `evaluation/results/performance_metrics.jsonl`. These files contain records from multiple runs; check the run ID and timestamp when using them as evidence.

The dashboard alert-state checks run separately with Node.js and do not count as pytest cases:

```bash
node --test evaluation/test_dashboard_alerts.mjs
```


## Repository layout

- `gateway/` contains the API routes, persistence, ABAC, detector, IoT policy engine, and response logic.
- `simulator/` contains the facility model, device simulators, MQTT publisher, and development attack scenarios.
- `shared/` contains request and data models used by both applications.
- `dashboard/src/` contains the React interface.
- `mosquitto/config/` contains the local broker configuration.
- `evaluation/` contains the pytest scenarios, alert checks, and recorded evaluation evidence.

