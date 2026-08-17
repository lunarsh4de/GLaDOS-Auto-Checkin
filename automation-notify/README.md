# Automation notifications

This directory is the single Feishu notification layer for all automation
tasks. New tasks integrate by writing a `task-status-v1` JSON report and using
`.github/actions/notify-automation`; the bot code does not need task-specific
updates.

Repository secrets:

- `FEISHU_WEBHOOK_URL`: custom-bot webhook
- `FEISHU_WEBHOOK_SECRET`: signing secret when signature verification is enabled

Files:

- `send-feishu.py`: validates reports and renders Feishu cards
- `task-status.schema.json`: machine-readable v1 report schema
- `STATUS_CONTRACT.md`: report and workflow integration guide
- `test_send_feishu.py`: adapter tests

The notification layer receives only user-facing task state. Credentials and
implementation details remain in task secrets and GitHub Actions logs.
