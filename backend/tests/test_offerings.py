"""Offerings CRUD, scoring, matching, and approval tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.database.connection import SessionLocal, init_db
from app.icp.models import IcpRecordRow
from app.offerings.ai_service import OfferingAIService
from app.offerings.match_batch_runner import process_match_job
from app.offerings.matching_service import match_icp_to_offering
from app.offerings.models import MATCH_STATUS_APPROVED, MATCH_STATUS_REJECTED, OfferingMatchRow, OfferingRow
from app.offerings.scoring import calculate_fit_score
from app.offerings.service import create_offering, update_offering


@pytest.fixture(autouse=True)
def _schema():
    init_db()


def _seed_icp(
    *,
    user_id: int = 1,
    name: str = "John Doe",
    company: str = "ABC BPO",
    designation: str = "VP Operations",
    industry: str = "BPO",
    company_size: str = "500-1000",
    about: str = "Responsible for agent performance and quality assurance in contact centers.",
) -> int:
    db = SessionLocal()
    try:
        row = IcpRecordRow(
            user_id=user_id,
            name=name,
            company_name=company,
            designation=designation,
            industry=industry,
            company_size=company_size,
            about=about,
            location="India",
            verification_status="VERIFIED",
            verified_at=datetime.now(timezone.utc),
            source="manual",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def _seed_offering(client, name: str = "AI Call Copilot") -> dict:
    resp = client.post(
        "/api/offerings",
        json={
            "name": name,
            "short_description": "AI-powered call coaching",
            "description": "Call quality monitoring and real-time coaching",
            "product_type": "SaaS",
            "target_industries": ["BPO", "Contact Centers"],
            "company_size_min": 200,
            "company_size_max": 5000,
            "target_departments": ["Operations", "Customer Experience"],
            "target_job_titles": ["VP Operations", "COO", "Contact Center Director"],
            "target_seniority": ["VP", "Director", "C-level"],
            "pain_points": ["call quality", "agent performance"],
            "use_cases": ["quality assurance", "coaching"],
            "positive_keywords": ["contact center", "QA"],
            "negative_keywords": ["intern"],
            "exclusion_rules": [],
            "buying_roles": ["Decision maker"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_offering_crud(client):
    created = _seed_offering(client)
    oid = created["id"]
    assert created["name"] == "AI Call Copilot"

    listed = client.get("/api/offerings")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    got = client.get(f"/api/offerings/{oid}")
    assert got.status_code == 200
    assert got.json()["target_industries"] == ["BPO", "Contact Centers"]

    updated = client.put(
        f"/api/offerings/{oid}",
        json={"name": "AI Call Copilot Pro", "target_industries": ["BPO", "Telecom"]},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "AI Call Copilot Pro"
    assert updated.json()["definition_version"] >= 2

    deleted = client.delete(f"/api/offerings/{oid}")
    assert deleted.status_code == 200
    assert client.get(f"/api/offerings/{oid}").status_code == 404


def test_generate_icp_validation(client):
    resp = client.post("/api/offerings/generate-icp", json={"description": "short"})
    assert resp.status_code == 422

    resp = client.post(
        "/api/offerings/generate-icp",
        json={
            "description": (
                "We sell an AI platform that analyzes customer calls, "
                "provides real-time coaching, and evaluates agents."
            )
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["industries"], list)
    assert isinstance(data["job_titles"], list)
    assert "pain_points" in data


def test_scoring_industry_and_title_match():
    offering = OfferingRow(
        name="Test",
        target_industries=["BPO", "Contact Centers"],
        target_job_titles=["VP Operations", "COO"],
        target_departments=["Operations"],
        target_seniority=["VP", "Director"],
        company_size_min=200,
        company_size_max=2000,
        pain_points=["agent performance"],
        use_cases=["quality assurance"],
        positive_keywords=["contact center"],
        hard_filter_rules={"require_industry_overlap": True},
    )
    icp = IcpRecordRow(
        name="John",
        company_name="ABC BPO",
        designation="VP Operations",
        industry="BPO",
        company_size="500-1000",
        about="Responsible for agent performance and quality assurance",
    )
    result = calculate_fit_score(offering, icp, semantic_similarity=70)
    assert result.industry_score >= 80
    assert result.role_fit_score >= 50
    assert result.fit_score >= 50
    assert result.match_tier in ("strong", "good", "potential")
    assert result.explanation


def test_hard_filter_blocks_industry_mismatch():
    offering = OfferingRow(
        name="Healthcare AI",
        target_industries=["Healthcare"],
        target_job_titles=["VP Operations"],
        hard_filter_rules={"require_industry_overlap": True},
    )
    icp = IcpRecordRow(
        name="Builder",
        designation="VP Operations",
        industry="Construction",
        about="Runs construction ops",
    )
    result = calculate_fit_score(offering, icp)
    assert result.hard_filtered is True
    assert result.fit_score == 0


def test_semantic_embedding_boosts_problem_fit():
    from app.offerings.embeddings import ensure_offering_embedding, semantic_similarity_score

    offering = OfferingRow(
        name="Support AI",
        target_industries=["E-commerce"],
        target_job_titles=["Head of Customer Support"],
        pain_points=["high support volume", "slow response time"],
        use_cases=["ticket automation"],
        hard_filter_rules={"require_industry_overlap": False},
    )
    ensure_offering_embedding(offering)
    icp = IcpRecordRow(
        name="Sam",
        designation="Head of Customer Support",
        industry="E-commerce",
        about="We are struggling to handle increasing customer queries while maintaining response time.",
    )
    sem = semantic_similarity_score(offering, icp)
    assert sem > 0
    result = calculate_fit_score(offering, icp, semantic_similarity=sem)
    assert result.problem_fit_score >= 0
    assert result.semantic_similarity == sem


def test_scoring_exclusion_zeros():
    offering = OfferingRow(
        name="Test",
        target_industries=["SaaS"],
        target_job_titles=["VP Sales"],
        exclusion_rules=["intern"],
        negative_keywords=[],
        hard_filter_rules={"require_industry_overlap": False},
    )
    icp = IcpRecordRow(
        name="Jane",
        designation="Sales Intern",
        industry="SaaS",
        about="Looking for internships",
    )
    result = calculate_fit_score(offering, icp)
    assert result.excluded is True
    assert result.fit_score == 0
    assert result.match_tier == "poor"


def test_duplicate_match_prevention_and_approval(client):
    offering = _seed_offering(client)
    icp_id = _seed_icp()
    oid = offering["id"]

    db = SessionLocal()
    try:
        off = db.query(OfferingRow).filter(OfferingRow.id == oid).one()
        icp = db.query(IcpRecordRow).filter(IcpRecordRow.id == icp_id).one()
        m1 = match_icp_to_offering(db, off, icp, use_ai=False, force=True)
        db.commit()
        mid = m1.id
        m2 = match_icp_to_offering(db, off, icp, use_ai=False, force=False)
        assert m2.id == mid
        count = (
            db.query(OfferingMatchRow)
            .filter(OfferingMatchRow.offering_id == oid, OfferingMatchRow.icp_record_id == icp_id)
            .count()
        )
        assert count == 1
    finally:
        db.close()

    approved = client.post(f"/api/offerings/{oid}/matches/{mid}/approve")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == MATCH_STATUS_APPROVED

    # ICP record still a single row
    icp_list = client.get("/api/icp")
    assert icp_list.status_code == 200
    names = [i["name"] for i in icp_list.json()["items"]]
    assert names.count("John Doe") == 1

    rejected = client.post(f"/api/offerings/{oid}/matches/{mid}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == MATCH_STATUS_REJECTED


def test_background_matching_job(client, monkeypatch):
    offering = _seed_offering(client)
    _seed_icp()
    _seed_icp(
        name="Rahul",
        company="Tech Corp",
        designation="Software Engineer",
        industry="Software",
        about="Builds APIs",
    )
    oid = offering["id"]

    # Avoid racing the background thread — run the worker inline.
    monkeypatch.setattr(
        "app.offerings.routes.start_match_job_async",
        lambda job_id, force=False: process_match_job(job_id, force=force, batch_size=10),
    )

    start = client.post(f"/api/offerings/{oid}/match", params={"force": True})
    assert start.status_code == 200, start.text
    assert start.json()["job_id"]

    status = client.get(f"/api/offerings/{oid}/matching-status")
    assert status.status_code == 200
    body = status.json()
    assert body["status"] == "done"
    assert body["processed_count"] >= 2

    matches = client.get(f"/api/offerings/{oid}/matches", params={"sort_by": "fit_score"})
    assert matches.status_code == 200
    items = matches.json()["items"]
    assert len(items) >= 2
    assert items[0]["fit_score"] >= items[-1]["fit_score"]


def test_definition_change_invalidates_skip():
    db = SessionLocal()
    try:
        off = create_offering(
            db,
            user_id=1,
            data={
                "name": "X",
                "target_industries": ["BPO"],
                "target_job_titles": ["VP Operations"],
            },
        )
        icp = IcpRecordRow(
            user_id=1,
            name="A",
            designation="VP Operations",
            industry="BPO",
            source="manual",
        )
        db.add(icp)
        db.flush()
        m1 = match_icp_to_offering(db, off, icp, use_ai=False, force=True)
        db.commit()
        mid = m1.id
        ver = m1.offering_definition_version

        # Same version → skip
        m_skip = match_icp_to_offering(db, off, icp, use_ai=False, force=False)
        assert m_skip.id == mid
        assert m_skip.offering_definition_version == ver

        update_offering(db, off, {"target_industries": ["Telecom"]})
        db.commit()
        db.refresh(off)
        assert off.definition_version == ver + 1

        m2 = match_icp_to_offering(db, off, icp, use_ai=False, force=False)
        assert m2.id == mid
        assert m2.offering_definition_version == off.definition_version
    finally:
        db.close()


def test_ai_schema_validation_accepts_lists():
    svc = OfferingAIService()
    payload = svc._validate_generated(
        {
            "industries": ["SaaS"],
            "company_size": {"min": 50, "max": 500, "label": "50-500"},
            "job_titles": "VP Sales",
            "pain_points": ["pipeline"],
        }
    )
    assert payload.industries == ["SaaS"]
    assert payload.job_titles == ["VP Sales"]


def test_recommendation_feedback_and_by_icp(client, monkeypatch):
    offering = _seed_offering(client)
    icp_id = _seed_icp()
    oid = offering["id"]

    monkeypatch.setattr(
        "app.offerings.routes.start_match_job_async",
        lambda job_id, force=False: process_match_job(job_id, force=force, batch_size=10),
    )
    start = client.post(f"/api/offerings/{oid}/match", params={"force": True})
    assert start.status_code == 200, start.text

    matches = client.get(f"/api/offerings/{oid}/matches")
    assert matches.status_code == 200
    items = matches.json()["items"]
    assert items
    mid = items[0]["id"]

    fb = client.post(f"/api/offerings/matches/{mid}/feedback", json={"action": "viewed"})
    assert fb.status_code == 200, fb.text
    assert fb.json()["action"] == "viewed"

    by_icp = client.get(f"/api/offerings/by-icp/{icp_id}", params={"min_score": 0, "limit": 5})
    assert by_icp.status_code == 200
    assert by_icp.json()["total"] >= 1
    assert "match_reasons" in by_icp.json()["items"][0]


def test_unverified_icp_excluded_from_match_job(client, monkeypatch):
    offering = _seed_offering(client)
    _seed_icp(name="Verified Person")
    db = SessionLocal()
    try:
        unverified = IcpRecordRow(
            user_id=1,
            name="Unverified",
            designation="VP Sales",
            industry="BPO",
            verification_status="PENDING",
            source="manual",
        )
        db.add(unverified)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        "app.offerings.routes.start_match_job_async",
        lambda job_id, force=False: process_match_job(job_id, force=force, batch_size=10),
    )
    start = client.post(f"/api/offerings/{offering['id']}/match", params={"force": True, "verified_only": True})
    assert start.status_code == 200
    body = start.json()
    # Only verified ICP should be queued
    assert body["total_count"] >= 1
    matches = client.get(f"/api/offerings/{offering['id']}/matches", params={"search": "Unverified"})
    assert matches.status_code == 200
    assert all(i.get("name") != "Unverified" for i in matches.json()["items"])
