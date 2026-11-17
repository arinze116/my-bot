# Telegram experience design

## Product, audience, and job

- **Product:** Hackathon Radar, a private opportunity-intelligence bot.
- **Audience:** Chinweuba, checking Telegram from a phone or desktop client.
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
| 🆕 | newly detected opportunity |
| 🟢 | ongoing opportunities |
| ⏰ | deadline within 72 or 24 hours |
| 🔄 | material event change |
| 💰 | prize or funding |
| ⏳ | application deadline |
| 🗓️ | event dates |
| 📍 | delivery format or location |
| 👥 | team constraints |
| 🎟️ | eligibility |
| 🧰 | technical focus |
| 📝 | opportunity brief |
| 🔎 | discovery source |
| 📡 | source health |
| 🎯 | owner filters |
| ⏯ | pause/resume push alerts |
| 🌅 | daily ongoing digest |
| 🔖 | saved bookmarks |
| 📈 | archive totals |
| 🌐 | source coverage |
| 🧭 | guidance or recovery |
| ⌨️ | command-grid visibility |

## Command desk

```text
┌─────────────┬─────────────┐
│ 🆕 New      │ 🟢 Ongoing │
├─────────────┼─────────────┤
│ ⏰ Soon     │ 🔖 Bookmarks │
├─────────────┼─────────────┤
│ 🎯 Filters  │ 📡 Sources  │
├─────────────┼─────────────┤
│ ⏯ Alerts   │ 🌅 Digest   │
├─────────────┼─────────────┤
│ 📈 Vault    │ ⌨️ Hide     │
└─────────────┴─────────────┘
```

- Layout: five rows and two native buttons per row. Discovery and saved decisions come first,
  controls second, archive visibility and keyboard recovery last.
- Voice: personal and terse; one heading plus only the requested data.
- Motion: none added. Telegram's native keyboard behavior is appropriate for a frequently used tool.
- Principles: decision first; buttons carry navigation emojis while response bodies stay quiet;
  preserve line breaks instead of collapsing views into paragraphs.

## Response density budgets

| View | Maximum meaningful lines |
|---|---:|
| Grid | 3 |
| Status | 3 |
| New / Ongoing / Soon | one linked event per line, default 10 |
| Bookmarks | one linked event and one Remove action per item, default 10 |
| Filters | 7 |
| Vault | 7 |
| Sources | one health row per observed source |
| Guide | 6 |

Event lists keep one complete opportunity on one line rather than repeating multi-line mini-cards.
Vault shows at most five source rows plus one compact overflow row. Empty, hidden, and
unknown-command states use two lines.

## Alert hierarchy

1. Alert type and opportunity title.
2. One facts line: dates, mode, prize.
3. Verified tags and clearly labelled inferred signals.
4. Filter-match explanation when owner filters are active.
5. Source list and first-seen time in WAT.
6. Native Open, Mute, and Bookmark actions.

Empty optional fields disappear. Known ISO dates become day-month-year copy. Provider text remains
escaped, and the Telegram button uses the validated absolute source URL.

## States

- **Empty New/Ongoing/Soon/Vault:** says nothing matches right now without implying source silence.
- **Empty Bookmarks:** points to the Bookmark action on alerts instead of leaving a dead end.
- **Removed bookmark:** updates the existing list message immediately and removes its action row.
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
| Empty/error/recovery states | passed | Two-line copy and regression tests. |
| Motion/reduced motion | not applicable | No custom motion. |
| Focus and keyboard | passed | Telegram-native controls plus `/start` and `/grid` fallback. |
| 390 px/desktop screenshots | blocked | No authenticated Telegram-client screenshot tool is available on the VPS. |
| Awkward data | passed | Escaping, bounded titles, preserved line breaks, density budgets, URL migration, and 4,096 cap tests. |
| Unsourced proof | passed | No user counts, ratings, or performance claims. |
