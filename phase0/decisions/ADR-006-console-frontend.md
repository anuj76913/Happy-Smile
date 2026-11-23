# ADR-006 — Serve the form and console from the backend, without React for now

| | |
|---|---|
| **Status** | Accepted for Phase 2; revisit before Phase 3 |
| **Plan item** | P2-03, P2-07 (implementation-plan §2 "Recommended stack") |
| **Deciders** | Engineering, PM |

## Context

The plan proposed React (e.g. Next.js) for the enquiry form and Leads console, noting that any default could change after Phase 0. Phase 2 has one week and needs two small screens that already exist as a tested static prototype.

## Decision

Phase 2 serves both pages as static HTML, CSS and plain JavaScript from the FastAPI app (`/` and `/console`), built from the Phase 1 prototype.

## Why

- **One origin:** the session cookie, CSRF header check and strict Content-Security-Policy are simple when pages and API share a host. A separate Next.js app needs CORS or a proxy.
- **No second toolchain** to set up, secure and run in CI during week 1.
- **The UI was already tested** at 320–1280 px in Phase 1; reusing it lowers risk.
- **Small:** about 600 lines of front-end code across the two screens.

## Consequences

- Phase 3 adds three more console tabs, dialogs and live timers. If the console code grows past roughly 1,500 lines, or needs shared components, move it to React with Vite. The API does not change.
- No inline scripts or styles are allowed (CSP `default-src 'self'`), so the code must keep building DOM through scripts and CSS classes.
