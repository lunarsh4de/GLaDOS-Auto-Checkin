# Automation notifications

This directory is the single Feishu notification layer for all automation
tasks. New tasks integrate by writing a  JSON report and using
 the bot code does not need task-specific
 updates.

 Repository secrets

 -  custom-bot webhook
 -  signing secret when signature verification is enabled

 Files

 -  validates reports and renders Feishu cards
 -  machine-readable v1 report schema
 -  report and workflow integration guide
 -  adapter tests

 The notification layer receives only user-facing task state. Credentials and
 implementation details remain in task secrets and GitHub Actions logs.
 