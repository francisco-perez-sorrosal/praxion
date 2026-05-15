# Upstream Issues

Issues filed on third-party open-source projects. Append-only log.

| Date | Repository | Issue | Title | Status | Workaround | Filed By |
|------|-----------|-------|-------|--------|------------|----------|
| 2026-04-06 | anthropics/claude-code | [#44075](https://github.com/anthropics/claude-code/issues/44075) | SubagentStart hooks not fired for background agents | open | lazy agent span creation in chronograph | user |
| 2026-04-26 | anthropics/claude-code | [#50486](https://github.com/anthropics/claude-code/issues/50486) | feat(plugins): namespace plugin skills with plugin name prefix like commands | open (commented +evidence) | accept asymmetric `/context` and slash-autocomplete rendering until upstream fix; +1'd related #50488, #43695, #41890 | user |
| 2026-05-08 | anthropics/claude-code | [#57493](https://github.com/anthropics/claude-code/issues/57493) | Agent tool spawn crashes with K.length on first invocation in v2.1.136 | open | prefer custom-plugin researcher over shipped `Explore` in many-plugin sessions; documented in `CLAUDE.md` Known Limitations and `rules/swe/swe-agent-coordination-protocol.md` Shipped-Explore-fallback note; tracked locally as td-021 | user |
| 2026-05-10 | openai/codex | [#18887](https://github.com/openai/codex/issues/18887) | Stop hook invalid JSON error is too opaque for unsupported fields | open (commented +evidence) | normalize legacy top-level `additionalContext` into strict event-specific `hookSpecificOutput` envelopes in the Praxion Codex bridge; prefer explicit `UserPromptSubmit` schema output | user |
| 2026-05-15 | anthropics/claude-code | [#59340](https://github.com/anthropics/claude-code/issues/59340) | `claude agents` silently refused from inside any Claude Code session — uninformative error masks the process-tree gate | open | `scripts/dispatch-reworks` instructs the user to run `claude agents` from a fresh Cursor pane outside the orchestrator session; documented in `CLAUDE.md` Known Claude Code Limitations; ~30 min diagnostic cost ruling out env-marker / daemon / auth-mode / subscription / version gates before identifying the parent-process one | user |
