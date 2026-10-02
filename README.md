# Bayt

Household finance demo built on [Portacode UniStack](https://github.com/portacode/UniStack).

## Current functionality

- Signup and login without email verification
- Assistant-first dashboard and personalized fictional bills
- Persistent bills, budgets, simulated payments, and conversation history
- Spending history and estimated forecasts
- Explicit manual payment simulation and budget-limited demo auto-pay checks
- User-scoped finance queries and AI context

This is a demo, not a production financial service. No email inbox or payment provider is connected. Uploaded private email/PDF samples are not included. AI has read-only finance context; write actions use explicit application controls. Live AI uses the host account's Portacode AI balance; model availability may change.

## Source and configuration

The Django application is in `core/`, with templates in `templates/core/`. Database migrations are included. The repository contains no live database, uploaded media, or deployment environment file. `.env.example` contains placeholders only; configure fresh private values before running. The included Docker Compose file builds the application from this source.

The inherited `portafile.yaml` is the original UniStack deployment definition and still targets upstream UniStack; it is not a Bayt deployment template yet.

Upstream application snapshots are bundled under `apps/`; see `VENDORED_APPS.md` and retained upstream notices for provenance. The upstream `.gitmodules` is retained as provenance only; this source export contains ordinary files rather than Git submodule entries.
