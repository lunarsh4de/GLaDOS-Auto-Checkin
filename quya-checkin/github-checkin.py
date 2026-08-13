
#!/usr/bin/env python3
"""Run Quya daily check-in from GitHub Actions without persisting session data."""

import json
import os
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

import requests

API_BASE = "https://api.quya.org/api/v1"
POINTS_BASE = "https://www.quya.org"
TIMEOUT = (10, 30)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required secret: {name}")
    return value


def load_accounts() -> list[str]:
    raw = required_env("QUYA_ACCOUNTS")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError("QUYA_ACCOUNTS must be a JSON array") from error
    if not isinstance(value, list) or not value or len(value) > 10:
        raise RuntimeError("QUYA_ACCOUNTS must contain between 1 and 10 accounts")
    accounts = [str(item).strip() for item in value]
    if any(not account or "@" not in account for account in accounts):
        raise RuntimeError("QUYA_ACCOUNTS contains an invalid account")
    if len(set(accounts)) != len(accounts):
        raise RuntimeError("QUYA_ACCOUNTS contains duplicate accounts")
    return accounts


def response_json(response: requests.Response, operation: str) -> dict[str, Any]:
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError as error:
        raise RuntimeError(f"{operation} returned an invalid response") from error
    if not isinstance(body, dict):
        raise RuntimeError(f"{operation} returned an invalid response")
    return body


def points_data(session: requests.Session) -> dict[str, Any]:
    body = response_json(
        session.get(f"{POINTS_BASE}/api/user/points/bootstrap", timeout=TIMEOUT),
        "Points status",
    )
    if body.get("code") != 0 or not isinstance(body.get("data"), dict):
        raise RuntimeError("Unable to read points status")
    return body["data"]


def check_account(email: str, password: str, probe_only: bool) -> str:
    with requests.Session() as session:
        login_response = response_json(
            session.post(
                f"{API_BASE}/auth/login",
                json={"email": email, "password": password},
                timeout=TIMEOUT,
            ),
            "Login",
        )
        if login_response.get("code") != 0 or not isinstance(login_response.get("data"), dict):
            raise RuntimeError("Login was rejected")
        login = login_response["data"]
        token = login.get("access_token")
        user = login.get("user")
        user_id = user.get("id") if isinstance(user, dict) else None
        if not isinstance(token, str) or len(token) < 20 or not user_id:
            raise RuntimeError("Login did not return a usable session")

        handoff = session.get(
            f"{POINTS_BASE}/points",
            params={"user_id": user_id, "token": token},
            timeout=TIMEOUT,
        )
        handoff.raise_for_status()
        status = points_data(session)
        if status.get("checked_in_today"):
            return "already_checked_in"
        if probe_only:
            return "ready"

        result = response_json(
            session.post(
                f"{POINTS_BASE}/api/user/points/checkin",
                json={},
                timeout=TIMEOUT,
            ),
            "Check-in",
        )
        if result.get("code") != 0:
            raise RuntimeError("Check-in was rejected")
        if not points_data(session).get("checked_in_today"):
            raise RuntimeError("Check-in could not be verified")
        return "checked_in_now"


def write_report(path: str | None, accounts: list[dict[str, Any]]) -> None:
    if not path:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps({"task": "quya_checkin", "accounts": accounts}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = ArgumentParser(description="Run Quya daily check-in")
    parser.add_argument(
        "--report-path",
        default=os.environ.get("QUYA_REPORT_PATH"),
        help="Write a sanitized account-status report to this JSON file",
    )
    args = parser.parse_args()

    report: list[dict[str, Any]] = []
    try:
        accounts = load_accounts()
        password = required_env("QUYA_PASSWORD")
    except Exception as error:  # noqa: BLE001
        print(f"Configuration failed ({error})", file=sys.stderr)
        write_report(args.report_path, report)
        return 1

    probe_only = os.environ.get("QUYA_PROBE_ONLY") == "1"
    failures = 0
    for index, email in enumerate(accounts, start=1):
        try:
            result = check_account(email, password, probe_only)
            labels = {
                "already_checked_in": "already checked in",
                "checked_in_now": "check-in completed",
                "ready": "session verified",
            }
            print(f"Account {index}: {labels[result]}")
            report.append(
                {
                    "index": index,
                    "label": f"云桥账号 {index}（{email}）",
                    "status": result,
                }
            )
        except Exception as error:  # noqa: BLE001
            failures += 1
            print(f"Account {index}: failed ({error})", file=sys.stderr)
            report.append(
                {
                    "index": index,
                    "label": f"云桥账号 {index}（{email}）",
                    "status": "failed",
                }
            )
        write_report(args.report_path, report)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
