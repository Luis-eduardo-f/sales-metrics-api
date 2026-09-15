"""Tests for /metrics/revenue and /metrics/top-products against the fixture dataset
documented in tests/conftest.py::_seed_fixture_data.
"""


def test_revenue_grouped_by_day(client, auth_headers):
    response = client.get("/metrics/revenue", params={"group_by": "day"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["cached"] is False
    assert data["total_revenue"] == 260.0

    buckets = {b["period"]: b for b in data["buckets"]}
    assert buckets["2024-01-05"]["revenue"] == 50.0
    assert buckets["2024-01-05"]["order_count"] == 2
    assert buckets["2024-01-20"]["revenue"] == 50.0
    assert buckets["2024-01-20"]["order_count"] == 1
    assert buckets["2024-02-10"]["revenue"] == 60.0
    assert buckets["2024-02-20"]["revenue"] == 100.0

    # Order #5 (2024-02-15) was cancelled and must not contribute a bucket at all.
    assert "2024-02-15" not in buckets


def test_revenue_grouped_by_month(client, auth_headers):
    response = client.get("/metrics/revenue", params={"group_by": "month"}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    buckets = {b["period"]: b for b in data["buckets"]}
    assert buckets["2024-01"]["revenue"] == 100.0
    assert buckets["2024-01"]["order_count"] == 3
    assert buckets["2024-02"]["revenue"] == 160.0
    assert buckets["2024-02"]["order_count"] == 2
    assert data["total_revenue"] == 260.0


def test_revenue_respects_date_range_filter(client, auth_headers):
    response = client.get(
        "/metrics/revenue",
        params={"group_by": "day", "start_date": "2024-02-01", "end_date": "2024-02-28"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total_revenue"] == 160.0
    assert all(bucket["period"].startswith("2024-02") for bucket in data["buckets"])


def test_revenue_start_after_end_returns_400(client, auth_headers):
    response = client.get(
        "/metrics/revenue",
        params={"start_date": "2024-02-01", "end_date": "2024-01-01"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "detail" in response.json()


def test_revenue_invalid_group_by_returns_422(client, auth_headers):
    response = client.get("/metrics/revenue", params={"group_by": "year"}, headers=auth_headers)
    assert response.status_code == 422


def test_revenue_second_identical_call_is_served_from_cache(client, auth_headers):
    first = client.get("/metrics/revenue", params={"group_by": "day"}, headers=auth_headers)
    second = client.get("/metrics/revenue", params={"group_by": "day"}, headers=auth_headers)

    assert first.json()["cached"] is False
    assert second.json()["cached"] is True
    assert first.json()["total_revenue"] == second.json()["total_revenue"] == 260.0


def test_revenue_different_params_do_not_share_cache_entry(client, auth_headers):
    day_response = client.get("/metrics/revenue", params={"group_by": "day"}, headers=auth_headers)
    month_response = client.get("/metrics/revenue", params={"group_by": "month"}, headers=auth_headers)

    assert day_response.json()["cached"] is False
    assert month_response.json()["cached"] is False


def test_top_products_ordering_and_limit(client, auth_headers):
    response = client.get("/metrics/top-products", params={"limit": 2}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert len(data["products"]) == 2
    assert data["products"][0]["name"] == "Widget C"
    assert data["products"][0]["revenue"] == 150.0
    assert data["products"][1]["name"] == "Widget B"
    assert data["products"][1]["revenue"] == 80.0


def test_top_products_excludes_cancelled_orders(client, auth_headers):
    response = client.get("/metrics/top-products", params={"limit": 10}, headers=auth_headers)
    data = response.json()

    assert len(data["products"]) == 3  # all 3 products appear, none from cancelled-only sales
    widget_a = next(p for p in data["products"] if p["name"] == "Widget A")
    # 2x$10 (order #1) + 1x$10 (order #2) = $30; the 5x$10 from cancelled order #5 is excluded.
    assert widget_a["revenue"] == 30.0
    assert widget_a["units_sold"] == 3


def test_top_products_invalid_limit_returns_422(client, auth_headers):
    response = client.get("/metrics/top-products", params={"limit": 0}, headers=auth_headers)
    assert response.status_code == 422
