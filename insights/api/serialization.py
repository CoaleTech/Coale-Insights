# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""JSON-safety for API payloads, with no ML dependencies.

This lives outside `insights.ml` on purpose. `insights.api.response` is imported
by every API module in the app, and importing `insights.ml.base` from it pulled
pandas and numpy — measured at 143 MB resident — into every gunicorn worker that
served any Insights endpoint, ML or not. On a memory-capped host that is the
difference between a worker surviving and being killed, and a killed worker is
answered by the gateway with an HTML 502 rather than JSON.
"""

import sys

# Exact types that are already JSON-safe. Matched by identity, never isinstance:
# `numpy.float64` is a genuine subclass of `float`, so an isinstance fast path
# here would hand orjson a numpy scalar and produce
# `TypeError: Type is not JSON serializable: numpy.float64` during response
# encoding -- after the endpoint's try/except has already returned.
_JSON_SAFE = frozenset({str, int, bool, bytes, type(None)})


def sanitize_for_json(obj):
    """Recursively convert numpy scalars and non-finite floats to JSON-safe values.

    Frappe serialises responses with orjson and sets no OPT_NUMPY flag, so a
    stray ``numpy.float64`` raises inside `frappe.utils.response.as_json`. That
    is past every `except` in the endpoint, and Frappe's own error handler
    re-encodes the same payload, so the second encode fails too and the request
    escapes the WSGI app: gunicorn answers with a bare HTML 500, which reaches
    the browser as "the server returned a gateway error".
    """
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if type(obj) in _JSON_SAFE:
        return obj

    # A numpy scalar cannot exist unless numpy has been imported, so consulting
    # sys.modules is exact — and it keeps numpy off the import path of every
    # non-ML endpoint that returns through `success()`.
    numpy = sys.modules.get("numpy")
    if numpy is not None and isinstance(obj, numpy.generic):
        return _finite(obj.item())
    if isinstance(obj, float):
        return _finite(obj)
    return obj


def _finite(value):
    """Replace NaN and +/-Infinity with 0.

    Both are legal Python floats and illegal JSON. orjson encodes them as `null`,
    which reaches a chart as a missing point rather than a zero, and the built-in
    json module writes the literals `NaN`/`Infinity`, which `JSON.parse` rejects
    outright. Division by zero in pandas yields infinity rather than NaN, so
    ratio and growth-rate fields hit this routinely.
    """
    if value != value or value in (float("inf"), float("-inf")):
        return 0
    return value
