import pytest

VALID_PAYLOAD = {
    "applicant_name": "Rahul Sharma",
    "applicant_email": "rahul@example.com",
    "mobile_number": "9876543210",
    "pan_number": "ABCDE1234F",
    "requested_amount": 5000000,
    "loan_purpose": "home_renovation",
    "monthly_income": 75000,
    "employment_type": "salaried",
    "employer_name": "Infosys Ltd",
    "date_of_birth": "2004-03-03",
}


@pytest.mark.asyncio
async def test_submit_application_success(client, auth_token):
    response = await client.post(
        "/api/v1/applications/",
        json=VALID_PAYLOAD,
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "credit_check_pending"
    assert data["pan_number"] == "ABCDE1234F"
    assert "id" in data


@pytest.mark.asyncio
async def test_submit_requires_auth(client):
    response = await client.post("/api/v1/applications/", json=VALID_PAYLOAD)
    assert response.status_code == 403  # No token = forbidden


@pytest.mark.asyncio
async def test_invalid_pan_rejected(client, auth_token):
    payload = {**VALID_PAYLOAD, "pan_number": "INVALID123"}
    response = await client.post(
        "/api/v1/applications/",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any("PAN" in str(e) for e in errors)


@pytest.mark.asyncio
async def test_duplicate_pan_rejected(client, auth_token):
    payload = {**VALID_PAYLOAD, "pan_number": "ZZZZZ9999Z"}
    headers = {"Authorization": f"Bearer {auth_token}"}
    # First submission -- should succeed
    r1 = await client.post("/api/v1/applications/", json=payload, headers=headers)
    assert r1.status_code == 202
    # Second submission same PAN -- should be rejected
    r2 = await client.post("/api/v1/applications/", json=payload, headers=headers)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_low_income_ineligible(client, auth_token):
    payload = {**VALID_PAYLOAD, "monthly_income": 5000, "pan_number": "LOWIC1234F"}
    response = await client.post(
        "/api/v1/applications/",
        json=payload,
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 422
    assert "eligibility" in response.json()["detail"]["error"]


@pytest.mark.asyncio
async def test_get_application(client, auth_token):
    # Creating an application first
    create_resp = await client.post(
        "/api/v1/applications/",
        json={**VALID_PAYLOAD, "pan_number": "FETCH1234F"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert create_resp.status_code == 202
    app_id = create_resp.json()["id"]

    # Fetching it
    get_resp = await client.get(
        f"/api/v1/applications/{app_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == app_id


@pytest.mark.asyncio
async def test_list_applications_requires_ops(client, auth_token, ops_token):
    # applicant role cannot list
    r1 = await client.get(
        "/api/v1/applications/",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert r1.status_code == 403

    # ops role can list
    r2 = await client.get(
        "/api/v1/applications/",
        headers={"Authorization": f"Bearer {ops_token}"},
    )
    assert r2.status_code == 200
    assert "items" in r2.json()


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

