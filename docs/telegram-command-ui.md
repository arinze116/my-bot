# Telegram experience design

## Product, audience, and job

- **Product:** Hackathon Radar, a private opportunity-intelligence bot.
- **Audience:** Arinze, checking Telegram from a phone or desktop client.
- **Job:** surface enough verified detail to decide whether an opportunity deserves attention in
  seconds, then make status and archive checks effortless.

## Brand direction

Hackathon Radar should feel like a calm private operations desk: early, precise, and useful. It does
not shout, gamify routine information, or add emoji decoration without meaning.

The editable avatar and production JPG live in `brand/`. Its palette is Midnight `#050B14`, Radar
cyan `#38E8FF`, Signal mint `#51F6A6`, Opportunity amber `#FFB454`, and Cloud `#F3F7FB`. Telegram
owns interface typography, background colors, contrast, focus, dark mode, button sizing, and native
motion.

## Emoji vocabulary

| Emoji | Meaning |
|---|---|
| 🚨 | newly detected opportunity |
| 💰 | prize or funding |
| ⏳ | application deadline |
| 🗓️ | event dates |
| 📍 | delivery format or location |
| 👥 | team constraints |
| 🎟️ | eligibility |
| 🧰 | technical focus |
| 📝 | opportunity brief |
| 🔎 | discovery source |
| 📡 | live worker pulse |
| ✨ | newest archive entries |
| 📈 | archive totals |
| 🌐 | source coverage |
| 🧭 | guidance or recovery |
| ⌨️ | command-grid visibility |

## Command desk

```text
┌─────────────┬─────────────┐
│ 📡 Pulse    │ ✨ Fresh    │
├─────────────┼─────────────┤
│ 📈 Vault    │ 🌐 Coverage │
├─────────────┼─────────────┤
│ 🧭 Guide    │ ⌨️ Hide     │
└─────────────┴─────────────┘
```

- Layout: three rows and two native buttons per row.
- Voice: personal, confident, concise; sentence case instead of system-console uppercase.
- Motion: none added. Telegram's native keyboard behavior is appropriate for a frequently used tool.
- Principles: decision first; one meaning per symbol; every response ends with clarity about what
  happens next.

## Alert hierarchy

1. Radar hit and opportunity title.
2. Decision fields: prize, deadline, dates, format, team, eligibility, focus.
3. Short provider brief.
4. Source provenance.
5. One-tap `View opportunity ↗` action.

Empty optional fields disappear. Known ISO dates become day-month-year copy. Provider text remains
escaped, and the Telegram button uses the validated absolute source URL.

## States

- **Empty Fresh/Vault:** says the radar is active and what will populate the view.
- **Unknown command:** restores the desk and gives one recovery action.
- **Hidden grid:** confirms alerts remain active and `/grid` restores controls.
- **Source error:** identifies the degraded source while confirming other sources continue.
- **Unauthorized chat:** ignored without disclosing archive or service information.
- **Legacy archive row:** shown as text when its pre-migration record has no stored URL.

## UI quality ledger

| Check | Status | Evidence |
|---|---|---|
| Plan and information hierarchy | passed | Alert hierarchy and command wireframe above. |
| Palette and identity | passed | SVG/JPG master in `brand/`; visually inspected at 1024 px. |
| Type and dark mode | delegated | Telegram-native client rendering. |
| Spacing and hit targets | passed | Native `ReplyKeyboardMarkup`; two short actions per row. |
| Empty/error/recovery states | passed | Dedicated copy and regression tests. |
| Motion/reduced motion | not applicable | No custom motion. |
| Focus and keyboard | passed | Telegram-native controls plus `/start` and `/grid` fallback. |
| 390 px/desktop screenshots | blocked | No authenticated Telegram-client screenshot tool is available on the VPS. |
| Awkward data | passed | HTML/Markdown escaping, bounded titles, URL migration, 4,096 cap tests. |
| Unsourced proof | passed | No user counts, ratings, or performance claims. |
