import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.models import Portfolio
from app.config import settings
from pymongo import AsyncMongoClient
from beanie import init_beanie
import asyncio

@pytest.mark.asyncio
async def test_portfolio_crud(mongodb_container):
    # Explicitly initialize Beanie with the test MongoDB
    client = AsyncMongoClient(settings.mongodb_uri)
    await init_beanie(database=client[settings.mongodb_db], document_models=[Portfolio])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create
        post_data = {"name": "Test Portfolio"}
        resp = await ac.post("/api/v1/portfolios", json=post_data)
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "Test Portfolio"
        assert created["version"] == 1
        portfolio_id = created["portfolioId"]

        # Get all
        resp = await ac.get("/api/v1/portfolios")
        assert resp.status_code == 200
        all_portfolios = resp.json()
        assert any(p["portfolioId"] == portfolio_id for p in all_portfolios)

        # Get one
        resp = await ac.get(f"/api/v1/portfolio/{portfolio_id}")
        assert resp.status_code == 200
        single = resp.json()
        assert single["portfolioId"] == portfolio_id
        assert single["name"] == "Test Portfolio"

        # Update (success)
        put_data = {
            "portfolioId": portfolio_id,
            "name": "Updated Portfolio",
            "dateCreated": single["dateCreated"],
            "version": single["version"]
        }
        resp = await ac.put(f"/api/v1/portfolio/{portfolio_id}", json=put_data)
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["name"] == "Updated Portfolio"
        assert updated["version"] == 2

        # Update (version conflict)
        put_data["version"] = 1  # old version
        resp = await ac.put(f"/api/v1/portfolio/{portfolio_id}", json=put_data)
        assert resp.status_code == 409

        # Delete (version conflict)
        resp = await ac.delete(f"/api/v1/portfolio/{portfolio_id}?version=1")
        assert resp.status_code == 409

        # Delete (success)
        resp = await ac.delete(f"/api/v1/portfolio/{portfolio_id}?version=2")
        assert resp.status_code == 204

        # Get after delete
        resp = await ac.get(f"/api/v1/portfolio/{portfolio_id}")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_v1_invalid_portfolio_id_returns_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/portfolio/not-an-object-id")
        assert resp.status_code == 404

        put_data = {
            "portfolioId": "not-an-object-id",
            "name": "Updated Portfolio",
            "version": 1
        }
        resp = await ac.put("/api/v1/portfolio/not-an-object-id", json=put_data)
        assert resp.status_code == 404

        resp = await ac.delete("/api/v1/portfolio/not-an-object-id?version=1")
        assert resp.status_code == 404
