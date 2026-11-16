# Telegram command-grid design

## Product, audience, job

- **Product:** Hackathon Radar, a private Telegram opportunity monitor.
- **Audience:** one owner checking the bot from a phone or desktop Telegram client.
- **Job:** expose health, recent captures, archive counts, and source coverage without requiring the
  owner to remember or browse a long command list.

## Interface plan

Telegram owns the palette, typography, focus ring, button height, dark mode, and motion. The bot
therefore uses native controls rather than simulated styling.

```text
┌─────────────┬─────────────┐
│ 📡 Status   │ 🆕 Latest   │
├─────────────┼─────────────┤
│ 📊 Stats    │ 🛰 Sources  │
├─────────────┼─────────────┤
│ ❓ Help     │ ⌨️ Hide     │
└─────────────┴─────────────┘
```

- Layout: three rows, two equally weighted native buttons.
- Voice: operational, concise, private; no marketing claims.
- Motion: none added. Telegram's native press/keyboard behavior is sufficient for a frequent-use
  dashboard.
- Principles: short thumb-friendly labels; useful information in one response; automatic alerts
  stay separate from command interactions.

## States

- **Empty latest/stats:** explains that the next successful poll will populate the archive.
- **Unknown command:** restores the grid and tells the owner to choose a tile.
- **Hidden keyboard:** confirms `/grid` restores it.
- **Network/API error:** logged without credentials; the scheduler and source alerts continue.
- **Unauthorized chat:** ignored without disclosing archive or service information.

## UI quality ledger

| Check | Status | Evidence |
|---|---|---|
| Plan and layout | passed | Two-column wireframe above; `GRID_MARKUP` contract test. |
| Palette/type/dark mode | not applicable | Controlled accessibly by the Telegram client. |
| Spacing and hit targets | passed | Native `ReplyKeyboardMarkup`; short labels; two buttons per row. |
| Empty/error states | passed | Dedicated command tests and responses. |
| Motion/reduced motion | not applicable | No custom motion. |
| Keyboard/focus | passed | Telegram-native reply keyboard and slash-command fallback. |
| 390px/desktop screenshots | blocked | No authenticated Telegram-client screenshot tool is available on the VPS. |
| Awkward data | passed | Titles truncate at 80 characters; response text is capped at 4,096. |
| Unsourced proof | passed | No user counts, ratings, or performance claims appear. |
