"""Manual bulk add of ICP contacts (JSON + Excel/CSV)."""

from __future__ import annotations

from io import BytesIO


def test_bulk_json_creates_contacts(client):
    resp = client.post(
        "/api/icp/bulk",
        json={
            "contacts": [
                {
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "email": "ada@example.com",
                    "company_name": "Analytical Engines",
                    "designation": "Mathematician",
                },
                {
                    "name": "Grace Hopper",
                    "email": "grace@example.com",
                    "company_name": "US Navy",
                },
            ]
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert body["updated"] == 0
    assert body["skipped"] == 0

    listed = client.get("/api/icp", params={"search": "Ada"})
    assert listed.status_code == 200
    names = [row["name"] for row in listed.json()["items"]]
    assert "Ada Lovelace" in names


def test_bulk_json_skips_empty_and_updates_duplicate(client):
    first = client.post(
        "/api/icp/bulk",
        json={
            "contacts": [
                {
                    "name": "Niklaus Wirth",
                    "company_name": "ETH Zurich",
                    "email": "niklaus@old.com",
                }
            ]
        },
    )
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 1

    second = client.post(
        "/api/icp/bulk",
        json={
            "contacts": [
                {},
                {
                    "name": "Niklaus Wirth",
                    "company_name": "ETH Zurich",
                    "email": "niklaus@new.com",
                },
            ]
        },
    )
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["created"] == 0
    assert body["updated"] == 1
    assert body["skipped"] == 1

    listed = client.get("/api/icp", params={"search": "Niklaus Wirth"})
    emails = [row["email"] for row in listed.json()["items"] if row["name"] == "Niklaus Wirth"]
    assert "niklaus@new.com" in emails


def test_bulk_upload_csv(client):
    csv = (
        "First Name,Last Name,Email,Company,Designation\n"
        "Priya,Nambiar,priya@acme.com,Acme,VP of Sales\n"
        "Roshan,Shenisetty,roshan@acme.com,Acme,Engineer\n"
    ).encode("utf-8")
    resp = client.post(
        "/api/icp/bulk-upload",
        files={"file": ("contacts.csv", BytesIO(csv), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["created"] == 2
    assert body["skipped"] == 0

    listed = client.get("/api/icp", params={"search": "Priya"})
    assert listed.status_code == 200
    assert any(row["name"] == "Priya Nambiar" for row in listed.json()["items"])


def test_bulk_rejects_empty_payload(client):
    resp = client.post("/api/icp/bulk", json={"contacts": []})
    assert resp.status_code == 400
