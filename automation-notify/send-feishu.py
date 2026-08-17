#!/usr/bin/env python3
"""Send automation status cards through a Feishu custom-bot webhook."""

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
    "running": ("运行中", "blue"),
    "needs_attention": ("需处理", "orange"),
}
STATUS_ALIASES = {
    "completed": "success",
    "failed": "failure",
}
ITEM_STATUS_LABELS = {
    "success": "完成",
    "completed": "完成",
    "checked_in_now": "签到完成",
    "already_checked_in": "今日已签到",
    "ready": "已就绪",
    "running": "运行中",
    "failure": "失败",
    "failed": "失败",
    "needs_attention": "需处理",
    "cancelled": "已取消",
    "skipped": "已跳过",
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


def normalized_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    status = STATUS_ALIASES.get(status, status)
    if status not in STATUS_CONFIG:
        raise RuntimeError(f"Unsupported task status: {status or 'empty'}")
    return status


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Task report field {field} must be a non-empty string")
    text = value.strip()
    if len(text) > 200:
        raise RuntimeError(f"Task report field {field} is too long")
    return text


def _reject_extra_fields(value: dict[str, Any], allowed: set[str], field: str) -> None:
    extras = sorted(set(value) - allowed)
    if extras:
        raise RuntimeError(f"Task report field {field} contains unsupported data: {extras[0]}")


def load_task_report(path: str) -> dict[str, Any]:
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError("Task report is not valid JSON") from error
    if not isinstance(report, dict):
        raise RuntimeError("Task report must be a JSON object")

    # Keep reports produced by the first Quya integration readable while all
    # new tasks use the versioned generic contract.
    if report.get("task") == "quya_checkin" and isinstance(report.get("accounts"), list):
        return {
            "version": 1,
            "task": {"id": "quya-checkin", "name": "云桥自动签到"},
            "status": "failure"
            if any(item.get("status") == "failed" for item in report["accounts"] if isinstance(item, dict))
            else "success",
            "items": report["accounts"],
        }

    if report.get("version") != 1:
        raise RuntimeError("Task report version must be 1")
    _reject_extra_fields(report, {"version", "task", "status", "summary", "items"}, "root")
    task = report.get("task")
    if not isinstance(task, dict):
        raise RuntimeError("Task report field task must be an object")
    _reject_extra_fields(task, {"id", "name"}, "task")
    _required_text(task.get("id"), "task.id")
    _required_text(task.get("name"), "task.name")
    normalized_status(report.get("status"))
    items = report.get("items", [])
    if not isinstance(items, list):
        raise RuntimeError("Task report field items must be an array")
    if len(items) > 50:
        raise RuntimeError("Task report contains too many items")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise RuntimeError(f"Task report item {index + 1} must be an object")
        _reject_extra_fields(item, {"label", "status"}, f"items[{index}]")
        _required_text(item.get("label"), f"items[{index}].label")
        _required_text(item.get("status"), f"items[{index}].status")
    summary = report.get("summary")
    if summary is not None:
        _required_text(summary, "summary")
    return report


def task_report_card(path: str) -> tuple[str, str, str]:
    report = load_task_report(path)
    task = report["task"]
    title = _required_text(task.get("name"), "task.name")
    status = normalized_status(report.get("status"))
    lines: list[str] = []
    summary = report.get("summary")
    if isinstance(summary, str) and summary.strip():
        lines.append(summary.strip())
    for item in report.get("items", []):
        label = _required_text(item.get("label"), "item.label")
        item_status = str(item.get("status", "")).strip().lower()
        status_label = ITEM_STATUS_LABELS.get(item_status, "状态未知")
        lines.append(f"- {label}: {status_label}")
    if not lines:
        lines.append("任务已完成，未提供检查项。")
    return title, status, "\n".join(lines)


def quya_message(path: str) -> str:
    """Backward-compatible helper retained for existing callers and tests."""
    return task_report_card(path)[2]


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
    parser.add_argument("--report", help="Render a task-status-v1 JSON report")
    parser.add_argument("--title", help="Notification title")
    parser.add_argument("--status", default="success", help="Final task status")
    parser.add_argument("--message", default="", help="Plain status message")
    parser.add_argument("--message-file", help="Read the status message from a text file")
    parser.add_argument("--quya-report", help=argparse.SUPPRESS)
    args = parser.parse_args()

    report_path = args.report or args.quya_report
    if report_path:
        title, status, message = task_report_card(report_path)
    else:
        if not args.title:
            raise RuntimeError("Provide --title when no task report is used")
        title = args.title.strip()
        status = normalized_status(args.status)
        message = read_message(args)
    if not message:
        raise RuntimeError("Provide --report, --message, or --message-file")
    send_card(required_env("FEISHU_WEBHOOK_URL"), title, status, message)
    print("Feishu notification sent")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001
        print(f"Feishu notification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
