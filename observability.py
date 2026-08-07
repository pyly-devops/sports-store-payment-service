"""Prometheus metrics and structured JSON logging (Milestone 8).

This file is deliberately IDENTICAL in all five Python services except for
SERVICE_NAME. There is no shared library repo to hold it, so it is duplicated
rather than abstracted — the same trade already accepted for
`seed/init-mongo.js`. The alternative considered and rejected was a
hand-rolled middleware on bare `prometheus_client`: it needs no dependency,
but it puts ~50 lines of easy-to-get-subtly-wrong code (histogram buckets,
label cardinality, self-exclusion) in five places instead of ~20 lines of
configuration. One pinned dependency is the smaller liability.

See docs/plans/stage8-plan-observability.md §3 and §4 in cloudcart-workspace.
"""

import logging

from prometheus_fastapi_instrumentator import Instrumentator
from pythonjsonlogger.json import JsonFormatter

SERVICE_NAME = "payment-service"


def configure_logging(level: int = logging.INFO) -> None:
    """Emit one JSON object per log line instead of plain text.

    The consumer is Loki, not a human tailing a terminal: LogQL can filter on
    a parsed JSON field, and can only regex a text line.

    `force=True` is load-bearing, not defensive. uvicorn installs its own
    handlers when it is imported, and `basicConfig` is documented to do
    NOTHING if the root logger already has handlers. Without force the JSON
    handler is silently never installed under uvicorn (so production logs stay
    plain text while the tests pass), and with a naive `addHandler` instead
    every line is emitted twice — once JSON, once uvicorn's text — and Loki
    ingests both.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            # `timestamp` and `level` are the conventional field names and the
            # ones Grafana's log view understands without extra configuration.
            rename_fields={"asctime": "timestamp", "levelname": "level"},
            # Redundant with the `app` label Alloy attaches from the pod, but
            # it costs nothing and makes a raw `kubectl logs` readable on its
            # own, without Loki in the picture.
            static_fields={"service": SERVICE_NAME},
        )
    )
    logging.basicConfig(handlers=[handler], level=level, force=True)


def instrument(app) -> None:
    """Expose /metrics for Prometheus to scrape.

    Every argument is passed explicitly even where it matches the library
    default. The label cardinality of this endpoint is a stated requirement of
    the milestone ("no user/order/request IDs in labels"), so it should be
    visible here rather than inherited from a dependency that could change it
    in a minor release.
    """
    Instrumentator(
        # 200/201/204 all become "2xx". Both the dashboard and the error-rate
        # alert ask "what fraction is failing", never "how many 201s", and
        # grouping keeps the series count flat as the API grows.
        should_group_status_codes=True,
        # THE label-cardinality control. The `handler` label is Starlette's
        # matched ROUTE TEMPLATE — "/api/orders/{order_id}" — never the
        # request path "/api/orders/ORD-2026-000001". Order and user IDs
        # therefore cannot reach Prometheus, because the value never contains
        # one in the first place. That is a property of where the value comes
        # from, not of a sanitising regex somebody has to maintain.
        should_group_untemplated=True,
        # ...but unmatched paths are still COUNTED, collapsed into a single
        # series. Ignoring them would hide a 404 flood, which is exactly the
        # shape of a broken gateway route or a scanner.
        should_ignore_untemplated=False,
        # /health is hit by a readiness and a liveness probe every few seconds
        # on every pod. Left in, it is the overwhelming majority of "request
        # rate" and the dashboard would mostly show the cluster talking to
        # itself. /metrics excludes itself for the same reason.
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
