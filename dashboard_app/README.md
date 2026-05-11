# Praxion Dashboard Web

Experimental replacement for the current `streamlit_app/` dashboard, implemented
under the neutral `dashboard_app/` path chosen by the systems-architect pass.

Goals:

- preserve the current read-only, filesystem-driven contract over `.ai-state/` and `.ai-work/`
- keep `/dashboard` and `praxion-dashboard` as the external launch surface
- raise the UX ceiling with a more professional, extensible web application shell
- avoid duplicating project state into a new persistence layer

Current scope of this slice:

- Next.js App Router scaffold
- `src/`-based package layout aligned to the ratified systems plan
- server-side artifact readers over the live project filesystem
- page shells for Architecture, Workshops, ADRs, Sentinel, Roadmap, Metrics, and Documentation

Expected runtime contract:

- `PRAXION_PROJECT_ROOT` (required): absolute path to the target Praxion project
- `PRAXION_DASHBOARD_POLL_SECONDS` (optional): workshops auto-refresh interval

Planned migration boundary:

- keep `streamlit_app/` until launcher/install/docs parity is verified
- switch `scripts/praxion-dashboard` only after the new app is runnable end-to-end
