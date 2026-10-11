# User-Invoked Skills

Authoring guidance for skills a person triggers by typing `/name` (`/praxion:name` when a plugin ships it): description length by consumer, `argument-hint`, argument substitution, invocation modes, runtime behavior and converting an old command file. Reference material for the [Skill Creator](../SKILL.md) skill; the frontmatter field table and the full superset live in [schema.md](schema.md#claude-code-frontmatter-superset), the shared "why" in [context-engineering-foundations.md](context-engineering-foundations.md).

## Contents

- [Description Length by Consumer](#description-length-by-consumer)
- [The `argument-hint` Rules](#the-argument-hint-rules)
- [Arguments and Dynamic Context](#arguments-and-dynamic-context)
- [Invocation Modes](#invocation-modes)
- [Runtime and Permissions](#runtime-and-permissions)
- [Silent Frontmatter-Parse Failures](#silent-frontmatter-parse-failures)
- [Converting a Command File](#converting-a-command-file)

## Description Length by Consumer

Who reads a skill's `description` depends on `disable-model-invocation`, and the two cases want opposite lengths. A model-invocable skill's description is the always-loaded listing entry and the only auto-invocation mechanism, so its trigger vocabulary is load-bearing: write as much as it needs (the `description` plus `when_to_use` listing cap is 1,536 characters) and never shorten it to satisfy a style guideline, because the body is read only after invocation and a shortened description degrades activation silently. A user-only skill (`disable-model-invocation: true`) leaves model context entirely; its description reaches only `/` autocomplete and the skill picker, so write one plain line, skip trigger terms nobody will match against, and put the detail in the body where the person who typed `/name` will see it. Guard every side-effecting skill (commit, push, release, deploy, post externally) with `disable-model-invocation: true`: it blocks model invocation and reclaims the listing budget.

A long `description` is also a parse hazard: a folded scalar (`description: >`) that runs ten lines pushes later keys out of sight, which is where malformed values survive review. Keep a long description a quoted single-line string.

## The `argument-hint` Rules

`argument-hint` tells a person what to type after `/name`; it has no model-facing role. A skill that takes no arguments omits the key entirely, because `argument-hint: ""` and a bare `argument-hint:` (YAML null) occupy the field while saying nothing and are not consistent with each other. A skill that takes arguments lists every option the body reads, flags included: a hint missing `--dry-run` reads as exhaustive while it is not. Always quote the value, unconditionally: `argument-hint: "[message]"`, never `argument-hint: [message]`, because YAML reads a leading `[` as a flow sequence and the unquoted form loads as a list while the quoted form loads as a string.

The two-flow-sequence trap: an unquoted `[<run_tag>] [--task-slug <slug>]` is two flow sequences on one line, which no YAML parser accepts, so the whole frontmatter block fails to load and takes `description` and `allowed-tools` with it (see [Silent Frontmatter-Parse Failures](#silent-frontmatter-parse-failures)). A hint such as `<skill-name>` parses as a string only because it does not begin with a bracket, so quote that one too.

## Arguments and Dynamic Context
<!-- last-verified: 2026-10-10 -->

Everything typed after the slash name reaches the body through `$ARGUMENTS`, as one string. Read arguments through it (or an indexed form) and nothing else; this is the form every Praxion workflow skill uses.

`$ARGUMENTS[N]` and the shorthand `$N` are zero-based: `$0` is the first argument, `$1` the second (probed live 2026-10-10). A body that reads `$1` for the first argument therefore receives the second one. When positions matter, read `$ARGUMENTS` and state an explicit token order in the body, with each optional token's default ("if this is empty or still a literal placeholder, use the default"). A shell-style default such as `${2:-dflt}` is not harness substitution; the model reads it as text. An index with no matching argument is documented to stay literal but rendered empty in the probe, so write the body so either outcome is harmless.

Without `arguments:` in the frontmatter, the harness appends `ARGUMENTS: <input>` to a body that carries no placeholder, including a skill that only declares `argument-hint`. Declaring named `arguments:` switches that automatic append off, even when the body never mentions the names (observed 2026-09-24, against the docs): the input then reaches the body only through a placeholder (`$ARGUMENTS`, `$N` or `$name`). Any skill that declares `arguments:` must carry one.

A placeholder written in explanatory prose is substituted exactly like a functional one, so a sentence such as "when the arguments are non-empty" is safe only if it names the placeholder deliberately; elsewhere describe the idea in words. A literal dollar amount such as a cost estimate is placeholder-shaped and must be escaped.

A bang-prefixed backtick-quoted command runs once, before the body renders, and its output replaces it, so the model sees live repository state rather than a description of it (a fenced block opened with three backticks and a bang does the same for several lines). Every command run this way needs matching `allowed-tools` coverage, or the user is prompted before the body renders, and a failing command aborts the render. The `@path` file-inclusion form is legacy; prefer the bang form for new work.

`${CLAUDE_SKILL_DIR}` substitutes the skill's own directory at load, for bundled scripts and assets; `${CLAUDE_PLUGIN_ROOT}` substitutes the plugin root, for repository-level scripts a plugin ships.

`$ARGUMENTS` may be empty because the person can always type the bare `/name`. Test three paths before shipping: no arguments (infer a sensible default or decline naming the missing input, never proceed on nothing), more arguments than the hint declares, and arguments with spaces, quotes or shell metacharacters.

## Invocation Modes

Four modes cover a skill's reach. Default: the person (`/name`) and the model can both invoke it, and its description sits in the always-loaded listing. `disable-model-invocation: true`: only the person can invoke it and its description leaves the listing, so it costs no model context. `user-invocable: false`: hidden from the `/` menu, invoked only by the model, with its description still in the listing; it is background knowledge the model loads on its own. `context: fork`: the body runs as the prompt of a new subagent of the `agent` type (`general-purpose` when omitted) that does not see the conversation, meaningful only for skills with an explicit task; `background` (Claude Code 2.1.218 or later) defaults to `true` so the result arrives when the subagent completes, and `background: false` waits for it in the invoking turn. `scripts/validate.py` still reports `user-invocable`, `context`, `model`, `effort` and `hooks` as unknown fields although the harness accepts them; expect that finding until the validator is aligned. The field table is in [schema.md](schema.md#claude-code-frontmatter-superset).

## Runtime and Permissions

`allowed-tools` pre-approves tools while the skill is active; it does not restrict, and every tool stays callable under your permission settings (use deny rules to block one). Whether Claude may invoke a skill is governed by `Skill(...)` permission rules; a deny rule blocks invocation but the description keeps its listing cost, while `disable-model-invocation: true` blocks and reclaims it. Plugin skills are scanned once at session start, so a skill added mid-session is invisible until a fresh session. Details: [Discovery and Live Reload](plugin-and-troubleshooting.md#discovery-and-live-reload) and [Permission Management](plugin-and-troubleshooting.md#permission-management).

## Silent Frontmatter-Parse Failures

Frontmatter that does not parse fails silently: the skill registers no `description` and no `allowed-tools`, nothing announces it, and grepping for a field name succeeds on a file the parser rejects. Parse the frontmatter with a real YAML loader (or run `claude plugin validate .`), and quote any value whose first character is YAML-significant or that contains a colon followed by a space. Failure shapes and fixes: [YAML Errors](plugin-and-troubleshooting.md#yaml-errors).

## Converting a Command File

To convert a legacy command file (`commands/<name>.md`) into a skill, keep behavior and change form only:

1. `git mv` it to `skills/<name>/SKILL.md` and add `name: <name>`, equal to the directory.
2. Keep a user-only workflow user-only with the exact, unquoted line `disable-model-invocation: true`; reshape its description to one plain line of at most 1024 characters without angle brackets. Keep a model-invocable workflow's description byte-identical.
3. Write `allowed-tools` as a one-line list; give `argument-hint` as one quoted line listing every option the body reads, or omit it when there are none.
4. Read arguments through `$ARGUMENTS` or an indexed form; drop shell-style defaults and escape literal dollar amounts.
5. Correct relative-link depth (one directory deeper) and say "skill" where prose names the artifact kind.
6. Leave procedure steps, tables and tone as they are, then invoke once with and without arguments.
