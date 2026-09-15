"""Tests for /customers and /customers/{id}/summary against the fixture dataset documented
in tests/conftest.py::_seed_fixture_data.
"""


def test_customer_summary_with_multiple_orders(client, auth_headers):
    response = client.get("/customers/1/summary", headers=auth_headers)  # Alice
    assert response.status_code == 200
    data = response.json()

    assert data["customer_id"] == 1
    assert data["name"] == "Alice Silva"
    assert data["order_count"] == 2
    assert data["total_spend"] == 90.0  # $40 (order #1) + $50 (order #3)
    assert data["first_order_date"] == "2024-01-05T10:00:00"
    assert data["last_order_date"] == "2024-01-20T09:30:00"


def test_customer_summary_cancelled_order_excluded_from_spend(client, auth_headers):
    response = client.get("/customers/4/summary", headers=auth_headers)  # Diego
    assert response.status_code == 200
    data = response.json()

    assert data["order_count"] == 1  # the order still counts...
    assert data["total_spend"] == 0.0  # ...but it was cancelled, so it contributes no revenue


def test_customer_summary_with_no_orders(client, auth_headers):
    response = client.get("/customers/6/summary", headers=auth_headers)  # Fatima
    assert response.status_code == 200
    data = response.json()

    assert data["order_count"] == 0
    assert data["total_spend"] == 0.0
    assert data["first_order_date"] is None
    assert data["last_order_date"] is None


def test_customer_summary_not_found_returns_404(client, auth_headers):
    response = client.get("/customers/9999/summary", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Customer 9999 not found."


def test_list_customers_pagination(client, auth_headers):
    first_page = client.get("/customers", params={"page": 1, "page_size": 2}, headers=auth_headers)
    assert first_page.status_code == 200
    data = first_page.json()

    assert data["total"] == 6
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert data["total_pages"] == 3
    assert [c["name"] for c in data["items"]] == ["Alice Silva", "Bob Santos"]

    second_page = client.get("/customers", params={"page": 2, "page_size": 2}, headers=auth_headers)
    assert [c["name"] for c in second_page.json()["items"]] == ["Carla Souza", "Diego Fernandes"]


def test_list_customers_filter_by_country_case_insensitive(client, auth_headers):
    response = client.get(
        "/customers", params={"country": "brazil", "page_size": 50}, headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    assert {c["name"] for c in data["items"]} == {"Alice Silva", "Bob Santos", "Fatima Costa"}


def test_list_customers_filter_with_no_matches(client, auth_headers):
    response = client.get("/customers", params={"country": "Atlantis"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 0
    assert data["items"] == []
    assert data["total_pages"] == 0


def test_list_customers_invalid_page_size_returns_422(client, auth_headers):
    response = client.get("/customers", params={"page_size": 1000}, headers=auth_headers)
    assert response.status_code == 422
