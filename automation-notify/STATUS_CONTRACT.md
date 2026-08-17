# Task status contract

Every automation writes the same user-facing JSON report. The shared Feishu
adapter discovers the task name and status from this report so adding a task
does not require changing the bot or its renderer.

json

  "version" 1
    "task" "id" "example-task" "name" ""
      "status" "success"
        "summary" "查。"
          "items" 
              "label" " 1" "status" "completed"
                  "label" " 2" "status" "needsattention"
                    



                    Supported task statuses are success failure cancelled skipped
                    running and needsattention. Common item statuses such as completed
                    checkedinnow alreadycheckedin ready and failed receive Chinese
                    labels automatically. Unknown item statuses are shown as .

                    Reports may contain user-approved account identifiers in label such as the
                    email address used to distinguish Quya accounts. They must never contain
                    passwords cookies webhook URLs signing secrets tokens raw API responses
                    stack traces or other implementation-only data.

                    Add the shared action after a new task step

                    yaml
                    - name Notify Feishu
                      if always
                        uses ./.github/actions/notify-automation
                          env
                              FEISHUWEBHOOKURL  secrets.FEISHUWEBHOOKURL 
                                  FEISHUWEBHOOKSECRET  secrets.FEISHUWEBHOOKSECRET 
                                    with
                                        report-path  runner.temp /example-status.json
                                            fallback-title 
                                                fallback-status  steps.example.outcome 


                                                The action sends the report when it exists and sends a simple failure card if
                                                the task stops before producing one. Keep the task step on continue-on-error
                                                true run the notification with if always then restore the original
                                                failure after notification when the workflow must fail visibly.
                                                