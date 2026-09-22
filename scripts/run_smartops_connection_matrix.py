"""Mint a local PAT then probe local + UAT without printing secrets."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from test_smartops_connection import probe, print_report  # noqa: E402

LOCAL = os.environ.get("LEADSENSE_LOCAL_URL", "http://127.0.0.1:8000")
UAT = os.environ.get("LEADSENSE_UAT_URL", "https://uat.leadsense.feuji.com")
PROVIDER_EMAIL = os.environ.get("LEADSENSE_PROVIDER_EMAIL", "provider.admin@feuji.com")
PROVIDER_PASSWORD = os.environ.get("LEADSENSE_PROVIDER_PASSWORD", "Provider@123")


def http_json(method: str, url: str, *, token: str | None = None, payload: dict | None = None, timeout: float = 20.0):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else {}
        except json.JSONDecodeError:
            parsed = {"detail": body[:300]}
        return exc.code, parsed


def mint_local_pat() -> tuple[str, str]:
    status, body = http_json(
        "POST",
        f"{LOCAL}/api/auth/login",
        payload={"email": PROVIDER_EMAIL, "password": PROVIDER_PASSWORD},
    )
    if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
        raise SystemExit(f"Local provider login failed ({status}): {body}")
    jwt = body["access_token"]
    suffix = uuid.uuid4().hex[:8]
    status, created = http_json(
        "POST",
        f"{LOCAL}/api/organizations",
        token=jwt,
        payload={
            "name": f"SmartOps Probe {suffix}",
            "owner_name": "Probe Admin",
            "owner_email": f"probe.admin.{suffix}@example.com",
            "pat_name": "SmartOps",
        },
    )
    if status != 201:
        raise SystemExit(f"Local onboard failed ({status}): {created}")
    org_id = created["organization_id"]
    pat = created["token"]["token"]
    return org_id, pat


def run_probe(label: str, base_url: str, pat: str, org_id: str, insecure: bool = False) -> bool:
    print("=" * 72)
    print(label)
    print("=" * 72)
    report = probe(base_url, pat, expected_org_id=org_id, insecure=insecure)
    print_report(report, pat)
    print()
    return report.ok


def main() -> int:
    org_id, pat = mint_local_pat()
    print(f"Minted local organization_id={org_id}")
    print()
    local_ok = run_probe("1) Same system that issued the ids (local LeadSense)", LOCAL, pat, org_id)
    uat_ok = run_probe(
        "2) Different system (UAT) using the same local ids",
        UAT,
        pat,
        org_id,
        insecure=True,
    )
    print("Summary")
    print(f"  local  : {'PASS' if local_ok else 'FAIL'}")
    print(f"  UAT    : {'PASS' if uat_ok else 'FAIL'}  (expected FAIL — ids are not portable)")
    if not local_ok:
        return 1
    if uat_ok:
        print("Unexpected: local ids authenticated on UAT.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
