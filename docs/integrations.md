# Agent integrations

Adapters deliver status to the local bridge. Plugins use `/api/session`; the
desktop fallback runs inside the bridge. They fail quietly when
the light is unavailable and never return a tool approval or deny decision.

| Adapter | Discovery/configuration | Notes |
|---|---|---|
| Codex | `$CODEX_HOME/hooks.json`, otherwise `~/.codex/hooks.json` | Native hook review/trust is required. Local runtime only. |
| Claude Code | `~/.claude/settings.json` | Exec-form hooks with an argument array; preserves unrelated settings. |
| OpenCode | `$XDG_CONFIG_HOME/opencode/plugins/agent-matrix.ts`, otherwise `~/.config/opencode/plugins/agent-matrix.ts` | Restart to load the plugin. Experimental. |
| Cline | `~/.cline/plugins/agent-matrix.ts` plus desktop bridge fallback | Start the bridge before your next prompt. Experimental. |

Each plugin entry point imports the adapter from the installation folder. Paths
are generated locally, not committed to the repository. Setup uses the Python
virtual environment it creates. Do not move the folder while integrations refer
to it. Running setup a second time with the same selection is safe; uninstall
before changing the selection or installation path.

## Event behavior

- Native hooks: session start → idle; prompt submitted → working; permissions or
  questions → needs input; tool completion → working; stop → completed; session
  end → removed. Claude's StopFailure → error. Codex Interrupt → idle.
- OpenCode: busy/retry → working; permission/question asked → needs input; reply
  → working after every pending question resolves; idle after work → completed;
  session error → error (abort → idle); deletion/disposal → removed.
- Cline: run start → working; delayed pre-tool phase or question → needs input;
  tool execution/results → working; run finish → completed, error, or idle on abort.

Cline's SDK adapter does not expose a separate permission event in the runtime plugin hook bag
used here. The adapter observes `beforeTool` and `tool-started`, with a 750 ms
debounce. A slow pre-tool extension can produce the same interval. This indicator
is advisory, and does not modify permission policy. Subagent statuses are tracked
separately within the parent session.

Cline Desktop 0.0.32 failed to load even a minimal SDK plugin on the development
machine. When Cline is selected in setup, `cline_desktop: true` enables a fallback
in the bridge. It opens Cline's local `sessions.db` and
`hub-events-hub-production.db` read-only, selecting only session identifiers,
workspace paths, timestamps, status events, tool names and approval identifiers.
It does not select prompts, answers, tool arguments/results, or credentials.
Question and approval events drive needs input; desktop exit or session detachment
clears the status. This internal database format can change with Cline updates.
A missing or unsupported database stops reporting and the ordinary lease expires.
The fallback starts tracking with the next run after the bridge starts; it does
not replay past successes. Keep the desktop bridge launcher running. Uninstall
disables the fallback, or set `cline_desktop` to false in `.local/config.json`
and restart the bridge. The SDK plugin remains available for other Cline hosts.

OpenCode and Cline send five-second heartbeats. Ongoing work stays fresh, but
completion timestamps stay unchanged so a green check expires normally. A missing
heartbeat expires the adapter's sessions after approximately 20–22 seconds.
The native hooks have no heartbeat: quiet working states expire after 15 minutes,
input waits after one hour, and errors after 30 minutes.

## Verified scope

Codex and Claude native events were observed on the original Windows deployment.
The newly generated installer commands are tested using temporary configuration
files, including command paths with spaces and shell metacharacters. OpenCode
1.18.34 and Cline desktop executable version 0.0.32 were present during development;
the OpenCode working/question/completion test was confirmed by the owner. Cline's
original plugin test produced no events. The desktop fallback has automated
coverage, has been checked against the installed database schema, and its live
purple-border working/question/completion test was confirmed by the owner.
Approval/error/cancellation checks remain pending in both apps. These version
observations are not minimum-version claims.

## Primary references

- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [OpenCode plugins](https://opencode.ai/docs/plugins/)
- [Cline SDK plugins](https://docs.cline.bot/sdk/plugins)

App event schemas may change independently of this project. Report the app
version and event name when an indicator behaves incorrectly; omit chat contents.
