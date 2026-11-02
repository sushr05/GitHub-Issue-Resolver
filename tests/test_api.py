"""Integration tests for FastAPI endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_index_repository_missing_path(client):
    response = await client.post("/index-repository", json={"repository_path": "/nonexistent/path"})
    assert response.status_code == 400


async def test_process_issue_invalid_github_url(client):
    response = await client.post("/process-issue", json={
        "title": "Test issue",
        "description": "Something is broken",
        "github_url": "https://github.com/nonexistent-owner-xyz/nonexistent-repo-xyz",
    })
    # Clone will fail → 500
    assert response.status_code == 500


async def test_run_tests_bad_path(client):
    response = await client.post("/run-tests", json={"repository_path": "/nonexistent"})
    assert response.status_code == 200
    data = response.json()
    assert data["passed"] is False
