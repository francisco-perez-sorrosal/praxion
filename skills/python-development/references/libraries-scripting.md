# Essential Libraries: Scripting / Automation

Part of the [Essential Libraries](essential-libraries.md) catalog. For small scripts and
automation where pulling in a framework would be overkill.

| Role | Library | Why | When not to reach for it |
|---|---|---|---|
| Shell-like scripting ergonomics | thin `subprocess` wrapper with `shlex` | For anything beyond a trivial `subprocess.run`, a thin wrapper reduces footguns (quoting, `shell=True` injection risk) | Simple one-liners are fine with stdlib `subprocess` directly |
| HTTP for quick scripts | **httpx** (sync mode) | Same library as the async case — one dependency covers both sync scripts and async services, avoids `requests`+`aiohttp` duplication | — |
| Path/file handling | stdlib **pathlib** | Already idiomatic and sufficient for nearly all scripting needs | — |
| Rich console output | **Rich** | Turns a plain script's stdout into readable, structured output cheaply | Genuinely trivial scripts with a handful of print statements |
| Retry/resilience for flaky calls | **tenacity** | Well-established decorator-based retry logic (backoff, jitter, exception filtering) — avoids hand-rolled retry loops | Simple scripts where a single retry-with-sleep is genuinely sufficient |
