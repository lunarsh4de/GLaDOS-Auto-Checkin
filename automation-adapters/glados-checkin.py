#!/usr/bin/env python3
"""Run the existing GLaDOS check-in and emit a task-status-v1 report."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHECKIN_PATH = ROOT / "checkin.py"


def load_checkin_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("glados_checkin_runtime", CHECKIN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load checkin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_report(path: str, items: list[dict[str, str]], status: str, summary: str) -> None:
    if not path:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            {
                "version": 1,
                "task": {"id": "glados-checkin", "name": "GLaDOS 自动签到"},
                "status": status,
                "summary": summary,
                "items": items,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    report_path = os.environ.get("GLADOS_REPORT_PATH", "").strip()
    captured: dict[int, dict[str, Any]] = {}
    runtime_error: Exception | None = None

    try:
        module = load_checkin_module()
        account_count = len(module.load_cookies())
        original_checkin_account = module.checkin_account

        def tracked_checkin_account(session: Any, cookie: str, index: int, exchange_plan: str | None = None) -> dict[str, Any]:
            result = original_checkin_account(session, cookie, index, exchange_plan)
            captured[index] = result
            return result

        module.checkin_account = tracked_checkin_account
        exit_code = int(module.main() or 0)
    except Exception as error:  # noqa: BLE001
        runtime_error = error
        account_count = max(len(captured), 1)
        exit_code = 1

    items: list[dict[str, str]] = []
    success_count = repeat_count = failure_count = 0
    for index in range(1, account_count + 1):
        account = captured.get(index)
        label = f"GLaDOS 账号 {index}"
        result = "fail"
        if account:
            email = str(account.get("email") or "").strip()
            if email and email != "unknown":
                label += f"（{email}）"
            result = str(account.get("result") or "fail")

        if result == "ok":
            item_status = "checked_in_now"
            success_count += 1
        elif result == "repeat":
            item_status = "already_checked_in"
            repeat_count += 1
        else:
            item_status = "failed"
            failure_count += 1
        items.append({"label": label, "status": item_status})

    if not account_count:
        status = "failure"
        summary = "未检测到可用账号。"
    elif runtime_error:
        status = "failure"
        summary = "签到任务运行异常。"
    else:
        status = "failure" if success_count == 0 and repeat_count == 0 else (
            "needs_attention" if failure_count else "success"
        )
        summary = (
            f"签到完成：成功 {success_count}，今日已签到 {repeat_count}，"
            f"失败 {failure_count}。"
        )

    write_report(report_path, items, status, summary)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
