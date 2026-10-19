"""Safe report failures with a log-correlated public reference."""
import logging
import uuid

from django.shortcuts import render

logger = logging.getLogger(__name__)


def engine_error_response(request, operation, status=503):
    reference = uuid.uuid4().hex[:12]
    logger.error("Report failed: operation=%s reference=%s", operation, reference, exc_info=True)
    return render(request, "analysis/engine_unavailable.html", {"error_reference": reference}, status=status)
