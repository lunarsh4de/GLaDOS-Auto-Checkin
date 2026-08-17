# Task status contract

Every automation writes the same user-facing JSON report. The shared Feishu
adapter discovers the task name and status from this report, so adding a task
does not require changing the bot or its renderer.

```json
{
  "version": 1,
  "task": {"id": "example-task", "name": "示例自动化"},
  "status": "success",
  "summary": "本次检查已完成。",
  "items": [
    {"label": "账号 1", "status": "completed"},
    {"label": "账号 2", "status": "needs_attention"}
  ]
}
```

Supported task statuses are `success`, `failure`, `cancelled`, `skipped`,
`running`, and `needs_attention`. Common item statuses such as `completed`,
`checked_in_now`, `already_checked_in`, `ready`, and `failed` receive Chinese
labels automatically. Unknown item statuses are shown as `状态未知`.

Reports may contain user-approved account identifiers in `label`, such as the
email address used to distinguish Quya accounts. They must never contain
passwords, cookies, webhook URLs, signing secrets, tokens, raw API responses,
stack traces, or other implementation-only data.

Add the shared action after a new task step:

```yaml
- name: Notify Feishu
  if: always()
  uses: ./.github/actions/notify-automation
  env:
    FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
    FEISHU_WEBHOOK_SECRET: ${{ secrets.FEISHU_WEBHOOK_SECRET }}
  with:
    report-path: ${{ runner.temp }}/example-status.json
    fallback-title: 示例自动化
    fallback-status: ${{ steps.example.outcome }}
```

The action sends the report when it exists and sends a simple failure card if
the task stops before producing one. Keep the task step on `continue-on-error:
true`, run the notification with `if: always()`, then restore the original
failure after notification when the workflow must fail visibly.
