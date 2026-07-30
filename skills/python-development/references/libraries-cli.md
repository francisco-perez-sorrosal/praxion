# Essential Libraries: CLI Tools

Part of the [Essential Libraries](essential-libraries.md) catalog.

| Role | Library | Why | When not to reach for it |
|---|---|---|---|
| Arg parsing (type-hint-driven) | **Typer** | Builds on Click, infers the CLI from function type hints/annotations — least boilerplate for straightforward CLIs, strong DX | Very large/complex CLIs with deeply custom parsing logic may find Click's explicit decorator model easier to control |
| Arg parsing (decorator, mature) | **Click** | The long-established, battle-tested base Typer builds on; huge plugin ecosystem, very stable API | Newer type-hint-first style (Typer) is less boilerplate for simple cases |
| Arg parsing (stdlib) | **argparse** | Zero-dependency, sufficient for small scripts and any project that wants to stay dependency-lean | Larger CLIs with subcommands, shared options, and rich help text benefit from Typer/Click's ergonomics |
| Terminal output/formatting | **Rich** | The standard for colorized/structured terminal output, tables, progress bars, tracebacks — extremely widely adopted, low-risk default | Simple scripts with no formatted-output need don't need the dependency |
| Terminal UI (interactive/full-screen) | **Textual** | From the Rich author; a full TUI framework (widgets, layouts, async) when a CLI needs an interactive dashboard rather than just formatted output | Overkill for a linear script that just prints progress/results |
| Packaging as executable | **PyInstaller** | The most mature, broadest platform/hook support for bundling a script + interpreter into a standalone binary | Produces large binaries — evaluate alternatives on a case-by-case basis, and verify their current maintenance status before adopting one, since this space changes fast |
