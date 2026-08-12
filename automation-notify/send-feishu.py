#!/usr/bin/env python3
"""Send a reusable status card through a Feishu custom-bot webhook."""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TIMEOUT_SECONDS = 20
STATUS_CONFIG = {
    "success": ("成功", "green"),
    "failure": ("失败", "red"),
    "cancelled": ("已取消", "grey"),
    "skipped": ("已跳过", "grey"),
}
QUYA_STATUS_LABELS = {
    "checked_in_now": "签到完成",
    "already_checked_in": "今日已签到",
    "ready": "会话已验证",
    "failed": "签到失败",
}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def read_message(args: argparse.Namespace) -> str:
    if args.message_file:
        return Path(args.message_file).read_text(encoding="utf-8").strip()
    return args.message.strip()


def quya_message(path: str) -> str:
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    accounts = report.get("accounts") if isinstance(report, dict) else None
    if not isinstance(accounts, list) or not accounts:
        return "未获取到账号状态。"
    lines = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        index = account.get("index")
        status = account.get("status")
        label = QUYA_STATUS_LABELS.get(str(status), "状态未知")
        lines.append(f"- 账号 {index}: {label}")
    return "\n".join(lines) or "未获取到账号状态。"


def signature(secret: str, timestamp: str) -> str:
    digest = hmac.new(
        f"{timestamp}\n{secret}".encode("utf-8"), b"", hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def send_card(webhook: str, title: str, status: str, message: str) -> None:
    status_label, template = STATUS_CONFIG.get(status, ("已完成", "blue"))
    body: dict[str, Any] = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": template,
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**执行状态：{status_label}**\n{message}",
                    },
                }
            ],
        },
    }
    secret = os.environ.get("FEISHU_WEBHOOK_SECRET", "").strip()
    if secret:
        timestamp = str(int(time.time()))
        body["timestamp"] = timestamp
        body["sign"] = signature(secret, timestamp)

    request = Request(
        webhook,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        raise RuntimeError(f"Feishu webhook returned HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError("Unable to reach Feishu webhook") from error

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise RuntimeError("Feishu webhook returned an invalid response") from error
    if not isinstance(result, dict) or result.get("StatusCode") not in (0, None):
        raise RuntimeError("Feishu webhook rejected the message")


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a Feishu automation status card")
    parser.add_argument("--title", required=True, help="Notification title")
    parser.add_argument("--status", default="success", help="success, failure, cancelled, or skipped")
    parser.add_argument("--message", default="", help="Plain status message")
    parser.add_argument("--message-file", help="Read the status message from a text file")
    parser.add_argument("--quya-report", help="Render an account-status report written by github-checkin.py")
    args = parser.parse_args()

    if args.quya_report:
        message = quya_message(args.quya_report)
    else:
        message = read_message(args)
    if not message:
        raise RuntimeError("Provide --message, --message-file, or --quya-report")
    send_card(required_env("FEISHU_WEBHOOK_URL"), args.title, args.status, message)
    print("Feishu notification sent")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001
        print(f"Feishu notification failed: {error}", file=sys.stderr)
        raise SystemExit(1)

