"""Tests for the RAG API."""

import pytest


def test_health_check():
    """Health endpoint returns 200 when Qdrant is available."""
    # This test requires Qdrant running locally
    # Mark as integration test
    pytest.skip("Requires Qdrant running")


def test_query_validation():
    """Query endpoint validates input."""
    from api.models import QueryRequest
    # Valid
    req = QueryRequest(question="How do I create a Kubernetes deployment?")
    assert req.question
    assert req.top_k == 5
    # Invalid — empty question
    with pytest.raises(Exception):
        QueryRequest(question="")
