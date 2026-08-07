"""Tests for the /metrics endpoint added in Milestone 8.

The cardinality test below is the important one. "No user/order/request IDs in
labels" is a stated requirement of the milestone, and the usual way it gets
broken is not a bad regex — it is somebody bumping the instrumentation
library, its default handler source changing from the route template to the
raw request path, and nothing anywhere noticing until Prometheus has a series
per idempotency key.
"""


def test_metrics_endpoint_is_served(client):
    response = client.get("/metrics")

    assert response.status_code == 200
    # The Prometheus text exposition format, not JSON.
    assert "text/plain" in response.headers["content-type"]


def test_metrics_include_request_and_process_stats(client):
    body = client.get("/metrics").text

    # Request count and duration come from the instrumentator...
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    # ...and process stats come free from prometheus_client's default
    # collectors, which is what covers the brief's "process stats".
    assert "process_resident_memory_bytes" in body


def test_health_and_metrics_are_excluded_from_request_metrics(client):
    """Probes must not drown out real traffic.

    /health is hit by a readiness and a liveness probe every few seconds on
    every pod. If it were counted, "request rate" on the dashboard would be
    almost entirely the cluster talking to itself.
    """
    client.get("/health")
    body = client.get("/metrics").text

    assert 'handler="/health"' not in body
    assert 'handler="/metrics"' not in body


def test_handler_label_is_the_route_template_not_the_request_path(client):
    """The label must carry the ROUTE, never the value substituted into it.

    This is the requirement stated as an executable assertion: the request
    below carries a real-looking idempotency key in the path, and it must appear in the
    label as the placeholder rather than the value. No credentials are sent, so
    the route matches, the auth dependency rejects it, and no database is
    touched — the route template is recorded either way.
    """
    client.get("/api/payments/idem-key-abc123")
    body = client.get("/metrics").text

    assert 'handler="/api/payments/{idempotency_key}"' in body
    assert "idem-key-abc123" not in body


def test_unmatched_paths_collapse_to_a_single_series(client):
    """A 404 flood must be visible, but must not create a series per URL.

    Two different nonexistent paths, each carrying something that looks like an
    identifier. Both are counted under a single "none" handler, and neither
    value reaches Prometheus.
    """
    client.get("/api/nope/ORD-2026-000001")
    client.get("/api/nope/507f1f77bcf86cd799439011")
    body = client.get("/metrics").text

    assert "ORD-2026-000001" not in body
    assert "507f1f77bcf86cd799439011" not in body
