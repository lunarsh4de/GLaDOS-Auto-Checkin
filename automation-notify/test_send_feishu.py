#!/usr/bin/env python3

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("send-feishu.py")
SPEC = importlib.util.spec_from_file_location("send_feishu", MODULE_PATH)
assert SPEC and SPEC.loader
SEND_FEISHU = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SEND_FEISHU)


class FakeResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class SendFeishuTests(unittest.TestCase):
    def test_generic_report_supplies_title_status_summary_and_items(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "task-status.json"
            report.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "task": {"id": "backup", "name": "备份任务"},
                        "status": "needs_attention",
                        "summary": "一个检查项需要处理。",
                        "items": [
                            {"label": "主数据库", "status": "completed"},
                            {"label": "归档存储", "status": "needs_attention"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                SEND_FEISHU.task_report_card(str(report)),
                (
                    "备份任务",
                    "needs_attention",
                    "一个检查项需要处理。\n"
                    "- 主数据库: 完成\n"
                    "- 归档存储: 需处理",
                ),
            )

    def test_quya_message_uses_account_email_labels_and_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "quya-status.json"
            report.write_text(
                json.dumps(
                    {
                        "task": "quya_checkin",
                        "accounts": [
                            {
                                "index": 1,
                                "label": "云桥账号 1（alpha@example.com）",
                                "status": "checked_in_now",
                            },
                            {
                                "index": 2,
                                "label": "云桥账号 2（bravo@example.com）",
                                "status": "already_checked_in",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                SEND_FEISHU.quya_message(str(report)),
                "- 云桥账号 1（alpha@example.com）: 签到完成\n"
                "- 云桥账号 2（bravo@example.com）: 今日已签到",
            )

    def test_invalid_report_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "task-status.json"
            report.write_text(
                json.dumps(
                    {
                        "version": 2,
                        "task": {"id": "task", "name": "Task"},
                        "status": "success",
                        "items": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "version must be 1"):
                SEND_FEISHU.load_task_report(str(report))

    def test_report_rejects_implementation_only_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "task-status.json"
            report.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "task": {"id": "task", "name": "Task"},
                        "status": "failure",
                        "items": [
                            {
                                "label": "Account",
                                "status": "failed",
                                "debug_response": "must not be sent",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "unsupported data"):
                SEND_FEISHU.load_task_report(str(report))

    def test_send_card_builds_a_success_card(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse({"StatusCode": 0})

        with patch.object(SEND_FEISHU, "urlopen", fake_urlopen):
            SEND_FEISHU.send_card(
                "https://example.invalid/webhook", "Test task", "success", "- item: done"
            )

        self.assertEqual(captured["timeout"], SEND_FEISHU.TIMEOUT_SECONDS)
        self.assertEqual(captured["body"]["msg_type"], "interactive")
        self.assertEqual(captured["body"]["card"]["header"]["template"], "green")
        self.assertIn("执行状态：成功", captured["body"]["card"]["elements"][0]["text"]["content"])


if __name__ == "__main__":
    unittest.main()
