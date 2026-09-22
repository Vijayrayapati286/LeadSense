#!/usr/bin/env python3
"""Probe LeadSense the way SmartOps (or any other system) does.

Copy this file to the other machine. It uses only the Python standard library.

  python test_smartops_connection.py --base-url http://127.0.0.1:8000 --pat pat_xxx --org-id org_xxx
  python test_smartops_connection.py --base-url https://uat.leadsense.feuji.com --pat pat_xxx --org-id org_xxx

Env fallbacks: LEADSENSE_BASE_URL, LEADSENSE_PAT, LEADSENSE_ORG_ID

A PAT and organization_id only work on the LeadSense instance that issued them.
A token minted on this laptop will not validate on UAT, and a UAT token will not
validate here.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

SMARTOPS_CHECKS = (
    ("GET", "/api/auth/me", "SmartOps Test connection (whoami)"),
    ("GET", "/api/organizations", "List bound organization"),
    ("GET", "/api/organizations/me", "Organization profile"),
    ("GET", "/api/v1/integrations/me", "Legacy integrations whoami"),
    ("GET", "/api/leads", "Leads list (org-scoped)"),
)


@dataclass
class CheckResult:
    name: str
    method: str
    path: str
    ok: bool
    status: int | None
    detail: str
    body: dict | list | None = None


@dataclass
class ProbeReport:
    base_url: str
    expected_org_id: str | None
    results: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(row.ok for row in self.results)


def mask_secret(value: str, keep: int = 6) -> str:
    if not value:
        return "(empty)"
    if len(value) <= keep * 2:
        return value[:2] + "…"
    return f"{value[:keep]}...{value[-4:]}"


def join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + (path if path.startswith("/") else f"/{path}")


def parse_body(raw: bytes) -> dict | list | str:
    text = raw.decode("utf-8", errors="replace")
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text[:300]


def request_json(
    method: str,
    url: str,
    *,
    token: str,
    timeout: float,
    insecure: bool,
) -> tuple[int, dict | list | str]:
    ctx = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    req = urllib.request.Request(
        url,
        method=method.upper(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "LeadSense-SmartOps-connection-probe/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, parse_body(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, parse_body(exc.read() or b"")
    except urllib.error.URLError as exc:
        raise ConnectionError(str(exc.reason or exc)) from exc


def _extract_org_id(path: str, body: dict | list | str | None) -> str | None:
    if isinstance(body, dict):
        if body.get("organization_id"):
            return str(body["organization_id"])
        if isinstance(body.get("items"), list) and body["items"]:
            first = body["items"][0]
            if isinstance(first, dict) and first.get("organization_id"):
                return str(first["organization_id"])
    if isinstance(body, list) and body and isinstance(body[0], dict):
        if body[0].get("organization_id"):
            return str(body[0]["organization_id"])
    return None


def _detail_for(path: str, status: int | None, body: dict | list | str | None, expected_org_id: str | None) -> tuple[bool, str]:
    if status is None:
        return False, "No HTTP response"
    if status != 200:
        if isinstance(body, dict) and body.get("detail"):
            return False, f"HTTP {status}: {body['detail']}"
        return False, f"HTTP {status}"

    org_id = _extract_org_id(path, body)
    if expected_org_id and org_id and org_id != expected_org_id:
        return False, f"organization_id mismatch: got {org_id}, expected {expected_org_id}"

    if path == "/api/auth/me":
        if not isinstance(body, dict) or "organization_id" not in body:
            return False, "whoami did not return organization_id (this host is still JWT-only)"
        token_status = str(body.get("token_status") or "")
        if token_status and token_status.lower() != "active":
            return False, f"token_status={token_status}"
        return True, f"organization_id={body.get('organization_id')} token_status={token_status or 'active'}"

    if path == "/api/organizations":
        if not isinstance(body, list):
            return False, "expected a JSON array of organizations"
        if expected_org_id and not any(
            isinstance(row, dict) and row.get("organization_id") == expected_org_id for row in body
        ):
            return False, f"bound org {expected_org_id} not in list"
        count = len(body)
        bound = body[0].get("organization_id") if body and isinstance(body[0], dict) else None
        return True, f"{count} org(s), bound={bound}"

    if path in {"/api/organizations/me", "/api/v1/integrations/me"}:
        if not isinstance(body, dict) or not body.get("organization_id"):
            return False, "missing organization_id"
        return True, f"organization_id={body.get('organization_id')}"

    if path == "/api/leads":
        if isinstance(body, dict) and "items" in body:
            return True, f"total={body.get('total', len(body.get('items') or []))}"
        return True, "ok"

    return True, "ok"


def probe(
    base_url: str,
    pat: str,
    *,
    expected_org_id: str | None = None,
    timeout: float = 20.0,
    insecure: bool = False,
) -> ProbeReport:
    report = ProbeReport(base_url=base_url.rstrip("/"), expected_org_id=expected_org_id)
    for method, path, name in SMARTOPS_CHECKS:
        url = join_url(report.base_url, path)
        try:
            status, body = request_json(method, url, token=pat, timeout=timeout, insecure=insecure)
            ok, detail = _detail_for(path, status, body, expected_org_id)
            report.results.append(
                CheckResult(name=name, method=method, path=path, ok=ok, status=status, detail=detail, body=body if isinstance(body, (dict, list)) else None)
            )
        except ConnectionError as exc:
            report.results.append(
                CheckResult(name=name, method=method, path=path, ok=False, status=None, detail=f"connection failed: {exc}")
            )
    return report


def print_report(report: ProbeReport, pat: str) -> None:
    print(f"Base URL : {report.base_url}")
    print(f"PAT      : {mask_secret(pat)}")
    if report.expected_org_id:
        print(f"Org ID   : {report.expected_org_id}")
    print()
    width = max(len(row.path) for row in report.results)
    for row in report.results:
        mark = "PASS" if row.ok else "FAIL"
        status = f"{row.status}" if row.status is not None else "—"
        print(f"  [{mark}] {row.method:4} {row.path.ljust(width)}  {status:>3}  {row.detail}")
    print()
    print("RESULT:", "PASS — this PAT/org works on this host" if report.ok else "FAIL — ids are invalid on this host, or this host is not PAT-aware yet")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test LeadSense PAT + organization_id from another system")
    parser.add_argument("--base-url", default=os.environ.get("LEADSENSE_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--pat", default=os.environ.get("LEADSENSE_PAT", ""))
    parser.add_argument("--org-id", default=os.environ.get("LEADSENSE_ORG_ID", "") or None)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--insecure", action="store_true", help="Skip TLS certificate verification")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    pat = (args.pat or "").strip()
    if not pat:
        print("Missing PAT. Pass --pat pat_… or set LEADSENSE_PAT.", file=sys.stderr)
        return 2
    report = probe(
        args.base_url,
        pat,
        expected_org_id=(args.org_id or None),
        timeout=args.timeout,
        insecure=args.insecure,
    )
    print_report(report, pat)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
