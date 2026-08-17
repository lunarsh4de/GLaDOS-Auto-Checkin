#!/usr/bin/env python3
"""Run the existing Quya check-in and normalize its status report."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHECKIN_PATH = ROOT / "quya-checkin" / "github-checkin.py"


def load_checkin_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("quya_checkin_runtime", CHECKIN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load Quya check-in script")
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
                "task": {"id": "quya-checkin", "name": "云桥自动签到"},
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
    report_path = os.environ.get("QUYA_REPORT_PATH", "").strip()
    legacy_items: list[dict[str, Any]] = []
    runtime_error: Exception | None = None

    try:
        module = load_checkin_module()
        exit_code = int(module.main() or 0)
        if report_path and Path(report_path).is_file():
            legacy_report = json.loads(Path(report_path).read_text(encoding="utf-8"))
            if isinstance(legacy_report, dict) and isinstance(legacy_report.get("accounts"), list):
                legacy_items = [item for item in legacy_report["accounts"] if isinstance(item, dict)]
    except Exception as error:  # noqa: BLE001
        runtime_error = error
        exit_code = 1

    items = [
        {
            "label": str(item.get("label") or "云桥账号"),
            "status": str(item.get("status") or "failed"),
        }
        for item in legacy_items
    ]
    success_count = sum(item["status"] == "checked_in_now" for item in items)
    repeat_count = sum(item["status"] == "already_checked_in" for item in items)
    failure_count = sum(item["status"] == "failed" for item in items)

    if runtime_error or not items:
        status = "failure"
        summary = "签到任务运行失败，未获得账号状态。"
    else:
        status = "failure" if failure_count == len(items) else (
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
