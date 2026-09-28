"""Shared fixtures and automatic evidence capture for system evaluation tests.

The harness treats the running Docker Compose stack as the system under test.
Each pytest case can declare a ``scenario`` marker; its final PASS/FAIL result,
timing, expectation, and failure detail are appended to CSV and JSONL evidence
files so initial failures and later re-tests can both be retained.
"""

from __future__ import annotations

import csv
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

GATEWAY_URL = os.getenv("EVAL_GATEWAY_URL", "http://localhost:8000").rstrip("/")
FACILITY_URL = os.getenv("EVAL_FACILITY_URL", "http://localhost:8001").rstrip("/")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("EVAL_REQUEST_TIMEOUT", "5"))
RESET_TIMEOUT_SECONDS = float(os.getenv("EVAL_RESET_TIMEOUT", "30"))
STARTUP_TIMEOUT_SECONDS = float(os.getenv("EVAL_STARTUP_TIMEOUT", "30"))
ITERATION = os.getenv("EVAL_ITERATION", "1")
RUN_ID = os.getenv(
    "EVAL_RUN_ID",
    f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
CSV_PATH = RESULTS_DIR / "test_results.csv"
JSONL_PATH = RESULTS_DIR / "test_results.jsonl"


def pytest_configure(config):
    """Register evaluation metadata used in the generated evidence files."""

    config.addinivalue_line(
        "markers", "scenario(id, description, expected): evaluation scenario metadata"
    )


def _wait_for_health(
    url: str, timeout_seconds: float = STARTUP_TIMEOUT_SECONDS
) -> dict:
    """Wait until a service health endpoint returns HTTP 200."""

    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None

    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{url}/health", timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}: {response.text}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(0.5)

    raise RuntimeError(f"Service at {url} did not become healthy: {last_error}")


class EvaluationClient(httpx.Client):
    """Allow the demo reset to complete without slowing down other requests."""

    def post(self, url, **kwargs):
        if httpx.URL(url).path == "/system/reset-demo-data":
            kwargs.setdefault("timeout", RESET_TIMEOUT_SECONDS)
        return super().post(url, **kwargs)


@pytest.fixture(scope="session")
def gateway_url() -> str:
    return GATEWAY_URL


@pytest.fixture(scope="session")
def facility_url() -> str:
    return FACILITY_URL


@pytest.fixture(scope="session")
def client():
    """Provide one HTTP client for a complete evaluation run."""

    with EvaluationClient(timeout=REQUEST_TIMEOUT_SECONDS) as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
def seeded_system(client):
    """Start every evaluation run from the predefined seeded demo state.

    Both services must already be running. The reset intentionally clears old
    runtime evidence in the gateway database, then rebuilds the facility
    simulator. Test evidence itself is written outside the containers and is
    therefore preserved across resets.
    """

    _wait_for_health(GATEWAY_URL)
    _wait_for_health(FACILITY_URL)

    response = client.post(f"{GATEWAY_URL}/system/reset-demo-data")
    assert response.status_code == 200, (
        "Could not reset the system to seeded state: "
        f"HTTP {response.status_code} {response.text}"
    )

    _wait_for_health(GATEWAY_URL)
    _wait_for_health(FACILITY_URL)
    return response.json()


def wait_for_200(
    client: httpx.Client, url: str, timeout_seconds: float = 15.0
) -> httpx.Response:
    """Poll an endpoint until it returns 200, useful for first telemetry."""

    deadline = time.monotonic() + timeout_seconds
    last_response: httpx.Response | None = None

    while time.monotonic() < deadline:
        try:
            response = client.get(url)
            last_response = response
            if response.status_code == 200:
                return response
        except httpx.HTTPError:
            pass
        time.sleep(0.25)

    if last_response is None:
        raise AssertionError(f"No response received from {url}")
    raise AssertionError(
        f"{url} did not return 200 within {timeout_seconds:.1f}s; "
        f"last response was HTTP {last_response.status_code}: {last_response.text}"
    )


def _scenario_metadata(item) -> tuple[str, str, str]:
    marker = item.get_closest_marker("scenario")
    if marker is None:
        return item.name, item.name, "Test assertions pass"

    scenario_id = str(
        marker.kwargs.get("id", marker.args[0] if marker.args else item.name)
    )
    description = str(marker.kwargs.get("description", item.name))
    expected = str(marker.kwargs.get("expected", "Test assertions pass"))
    return scenario_id, description, expected


def _append_result(record: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    csv_exists = CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(record.keys()))
        if not csv_exists:
            writer.writeheader()
        writer.writerow(record)

    with JSONL_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Append one evidence row after the test's call phase finishes."""

    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return

    scenario_id, description, expected = _scenario_metadata(item)
    status = "PASS" if report.passed else "FAIL" if report.failed else "SKIP"

    if report.passed:
        actual = "Observed behaviour matched all assertions."
    elif report.failed:
        actual = str(report.longrepr)
    else:
        actual = str(report.longrepr or "Test skipped")

    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": RUN_ID,
        "iteration": ITERATION,
        "scenario_id": scenario_id,
        "test_name": item.name,
        "description": description,
        "expected": expected,
        "actual": actual,
        "status": status,
        "duration_ms": round(report.duration * 1000.0, 3),
    }
    _append_result(record)
