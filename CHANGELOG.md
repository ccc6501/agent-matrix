# Changelog

## 0.1.1 — preview

- Fix Cline Desktop staying off when its SDK plugin loader fails: the bridge now
  supports a read-only desktop status fallback, enabled when Cline is selected in setup.
- Track native questions and approvals, preserve success expiry, and clear closed sessions.
- Disable the desktop fallback on uninstall; add seven regression tests.
- Record owner-confirmed OpenCode and Cline working/question/completion tests.

Upgrading from 0.1.0: stop the old bridge, replace the source files in the same
installation folder, and rerun setup with the same agent selection. Keep `.local/`
and `.venv/` so the existing install manifest and settings remain available.
Relaunch Agent Matrix before sending your next Cline prompt. No board reflash is
needed for this update. If installing into a different folder, uninstall the old
integrations first. Approval/error/cancellation tests in the native apps and a
second-PC setup remain pending; see docs/testing.md.

## 0.1.0 — preview

- Four agent identity borders and shared status symbols on an 8×8 USB matrix.
- Local dashboard, desktop launcher, 72-second demo and rotation control.
- Codex/Claude hooks and experimental OpenCode/Cline plugins.
- Thirty-second success expiry and session/process/adapter cleanup.
- Windows setup, reversible integration registration, diagnostics and firmware copier.
- Machine-local configuration, safer HTTP validation, and automated release checks.

This is the first public preview. Native OpenCode/Cline and second-PC checks
remain pending; see docs/testing.md.
