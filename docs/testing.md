# Validation record and manual checks

The v0.1.0 preview adds portable setup, uninstall, board selection and API checks
to an existing hardware-tested prototype. Automated checks do not certify every
agent version or replace testing a physical board.

## Automated checks

- Matrix coordinates, four colors, urgent selection, rotation, and animation.
- Success expiry, stale events, process exit and PID reuse, adapter heartbeat loss.
- API rejects malformed objects, non-finite/future timestamps, oversized requests,
  incorrect content types, boolean command values, and foreign browser origins.
- Setup preserves unrelated hooks and settings; reruns do not duplicate entries.
- Uninstall preserves later user changes and modified plugins; failed writes roll back.
- Board discovery refuses ambiguous devices.
- Windows Codex hook wrapper preserves stdin and paths containing spaces, quotes,
  ampersands and dollar signs.
- JavaScript adapter events and dashboard script/element consistency.

GitHub Actions runs Python 3.12/3.13 on Windows. No hardware or model credentials
are required by CI. Test fixtures use temporary homes; they do not alter real
agent settings or submit prompts to models.

For this first preview, **29 Python tests passed locally on Python 3.12**, along
with both JavaScript checks and PowerShell parsing. The first hosted CI jobs did
not start, so Python 3.13 and the hosted-runner environment are not yet verified.
Workflow configuration is included for a later hosted run.

## Physical and native-agent checks

| Check | Status |
|---|---|
| Four agents acknowledged and selected by actual USB firmware | Passed on prototype |
| Publishable bridge: handshake, four-agent demo, API routing and cleanup on physical board | Passed |
| Complete setup script in a fresh local folder and virtual environment (manual mode) | Passed locally; second PC still pending |
| Serial heartbeat timeout/recovery and rotation | Passed on prototype |
| Blue spinner, corrected orange border and green check | Visually confirmed by owner |
| Native Codex and Claude hook events | Observed on original installation |
| Native OpenCode work → question/approval → success/error/cancel | Pending |
| Native Cline work → question/approval → success/error/cancel | Pending |
| White and purple physical color appearance | Pending owner confirmation |
| Physical USB unplug/replug while running | Pending |
| Fresh install on a second Windows PC | Pending |

For each agent: start two sessions, finish one, request input in the other, then
cancel and close it. Verify that one session ending does not clear another. Close
the entire application and check that stale status clears. Repeat with the bridge
temporarily stopped; the agent should continue unaffected. Do not use a running
production task as a cancellation test.

Mark an experimental integration verified only after testing its actual native
events and recording the app version. Keep the release labeled preview until the
remaining manual checks have been completed.
