import json
import logging
import socket
import sys

import pytest
import redis
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import health as health_module
from app.core.logging_config import JsonFormatter, RequestIdFilter, request_id_context
from app.main import app
from tests.factories import auth_headers, make_doctor, make_slot, make_user


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_when_dependencies_are_up(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok", "redis": "ok"}


def test_ready_reports_redis_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    broken_redis = redis.Redis(host="localhost", port=1, socket_connect_timeout=0.1)
    monkeypatch.setattr(health_module, "get_redis", lambda: broken_redis)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NOT_READY"
    assert response.json()["checks"]["redis"] == "unavailable"


def test_every_response_has_a_request_id(client: TestClient) -> None:
    response = client.get("/health")
    assert len(response.headers["X-Request-ID"]) == 32


def test_every_response_names_the_instance_that_served_it(client: TestClient) -> None:
    response = client.get("/health")
    assert response.headers["X-Served-By"] == socket.gethostname()


def test_incoming_request_id_is_reused_if_safe(client: TestClient) -> None:
    good = client.get("/health", headers={"X-Request-ID": "from-nginx-123"})
    bad = client.get("/health", headers={"X-Request-ID": "has spaces and <script>"})

    assert good.headers["X-Request-ID"] == "from-nginx-123"
    assert bad.headers["X-Request-ID"] != "has spaces and <script>"


def test_request_log_line_is_json_with_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/", headers={"X-Request-ID": "trace-me-42"})

    finished = [record for record in caplog.records if record.getMessage() == "Request finished"][0]
    log_line = json.loads(JsonFormatter().format(finished))
    assert log_line["request_id"] == "trace-me-42"
    assert log_line["status_code"] == 200
    assert log_line["path"] == "/"
    assert "duration_ms" in log_line


def test_filter_adds_request_id_from_context() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    token = request_id_context.set("abc123")
    RequestIdFilter().filter(record)
    request_id_context.reset(token)

    output = json.loads(JsonFormatter().format(record))
    assert output["message"] == "hello world"
    assert output["request_id"] == "abc123"


def test_formatter_includes_exceptions() -> None:
    try:
        raise ValueError("bad value")
    except ValueError:
        record = logging.LogRecord("test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    output = json.loads(JsonFormatter().format(record))
    assert "ValueError: bad value" in output["exception"]


def test_metrics_endpoint_exposes_http_and_booking_metrics(client: TestClient, db: Session) -> None:
    slot = make_slot(db, make_doctor(db))
    client.post("/api/bookings", json={"slot_id": slot.id}, headers=auth_headers(make_user(db)))

    metrics = client.get("/metrics").text

    assert "http_requests_total" in metrics
    assert "http_request_duration_seconds" in metrics
    assert "medislot_bookings_created_total" in metrics
    assert "medislot_booking_conflicts_total" in metrics


def test_unexpected_errors_hide_internal_details() -> None:
    def crash() -> None:
        raise RuntimeError("database password is hunter2")

    app.add_api_route("/test-only/crash", crash)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/test-only/crash")
    finally:
        app.router.routes = [
            route for route in app.router.routes if getattr(route, "path", "") != "/test-only/crash"
        ]

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "Something went wrong. Please try again later."}
    }
    assert "hunter2" not in response.text


def test_health_checks_are_not_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/health")
    assert "Request finished" not in caplog.text
