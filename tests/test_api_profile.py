from fastapi.testclient import TestClient

from signal_scribe.api import app, get_settings, profile_service_dependency
from signal_scribe.config import Settings
from signal_scribe.profile_contracts import V1Company, V1CompanyProfileResponse, profile_not_found


class _FakeProfileService:
    def __init__(self, response: V1CompanyProfileResponse) -> None:
        self._response = response

    async def get_company_profile(self, _ticker: str) -> V1CompanyProfileResponse:
        return self._response


def _client_with_profile(response: V1CompanyProfileResponse) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: Settings(signal_scribe_api_key="test-key")
    app.dependency_overrides[profile_service_dependency] = lambda: _FakeProfileService(response)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_company_profile_route_returns_available_profile():
    client = _client_with_profile(
        V1CompanyProfileResponse(
            status="available",
            company=V1Company(ticker="AAPL", cik="0000320193", name="Apple Inc."),
        )
    )

    response = client.get(
        "/v1/companies/aapl/profile",
        headers={"Authorization": "Bearer test-key"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "available"
    assert response.json()["company"]["ticker"] == "AAPL"


def test_company_profile_route_returns_404_for_not_found_ticker():
    client = _client_with_profile(profile_not_found("ZZZZ"))

    response = client.get(
        "/v1/companies/zzzz/profile",
        headers={"Authorization": "Bearer test-key"},
    )

    assert response.status_code == 404
    assert response.json()["status"] == "not_found"
    assert "ZZZZ" in response.json()["message"]


def test_company_profile_route_rejects_missing_auth():
    client = _client_with_profile(
        V1CompanyProfileResponse(
            status="available",
            company=V1Company(ticker="AAPL"),
        )
    )

    response = client.get("/v1/companies/aapl/profile")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"
