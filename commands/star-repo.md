---
description: Star the Praxion repo on GitHub
allowed-tools: [Bash(gh:*), AskUserQuestion]
disable-model-invocation: true
---

Interactive prompt to star the [Praxion](https://github.com/francisco-perez-sorrosal/Praxion) repository on GitHub.

## Procedure

1. Check if `gh` CLI is available and the user is authenticated:

   ```bash
   gh auth status &>/dev/null
   ```

2. **If both are true:**

   Ask the user with `AskUserQuestion`:

   > If you're enjoying Praxion, would you like to support the project by starring it on GitHub?

   Options:
   - "Please, star it! ⭐"
   - "No thanks 😢"
   - "Maybe later 🤷"

   If the user chooses **"Please, star it!"**, run:

   ```bash
   gh api -X PUT /user/starred/francisco-perez-sorrosal/Praxion 2>/dev/null
   ```

   - On success (exit code 0): thank the user for the support
   - On failure: display a fallback message with the repo URL for manual starring

   If the user chooses **"No thanks"** or **"Maybe later"**, acknowledge and move on.

3. **Otherwise:**

   Skip the question entirely. Display a brief message:

   > Github not available or user not auth. Please, star the project at [Praxion on GitHub](https://github.com/francisco-perez-sorrosal/Praxion)

## Constraints

- Never block or interrupt other workflows — fail gracefully at every step
- Do not retry on failure — show the manual URL and move on
- Keep output minimal — one or two sentences at most
