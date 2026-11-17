# Source contract research — 2026-11-17

## Executive summary

ETHGlobal is implementable from its public official `/events` page. Its guessed `/api/events` path returns 404, so the connector parses public event cards and keeps only hackathons. Luma discovery is not safely implementable without owner-provided authenticated access: the official discover page does not render query results server-side, and the endpoint used by Luma's official client returns 401 when unsigned. The bot marks Luma unavailable instead of bypassing access controls.

## Findings

- **VERIFIED — ETHGlobal public events:** `https://ethglobal.com/events` returned HTTP 200 and public cards with titles, dates, locations, event type, and canonical `/events/<slug>` links.
- **VERIFIED — no public ETHGlobal route at the guessed contract:** `https://ethglobal.com/api/events` returned HTTP 404 on 2026-11-17.
- **VERIFIED — Luma discover shell:** `https://luma.com/discover?query=hackathon` returned HTTP 200, but its `__NEXT_DATA__` contained places, calendars, and categories rather than query event results.
- **VERIFIED — Luma client search requires sign-in:** Luma's own shipped client bundle calls `https://api.luma.com/search/get-results?query=...`; the unsigned request returned HTTP 401 with `You are not signed in.`
- **DECISION:** implement ETHGlobal HTML parsing with deterministic fixtures. Leave Luma disabled/unimplemented until a documented public feed or owner-authorized API is available.

## Risks and counterpoints

Public HTML is an undocumented contract and may change. Parser fixtures detect known-shape regressions but cannot guarantee future compatibility. Search-engine scraping might find Luma pages, but it would add another indirect, incomplete contract and contradict the PRD preference for official surfaces.

## Sources

- https://ethglobal.com/events
- https://ethglobal.com/api/events
- https://luma.com/discover?query=hackathon
- https://api.luma.com/search/get-results?query=hackathon
