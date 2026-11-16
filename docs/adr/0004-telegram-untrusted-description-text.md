# ADR-0004: Keep untrusted Telegram descriptions out of Markdown entities

- Date: 2026-11-17 Africa/Lagos
- Status: accepted
- Rule ids affected: R-DELIVERY-1

## Context

An X description containing an escaped underscore in a handle and a trailing URL was wrapped in a
legacy Markdown italic entity. Telegram rejected the alert with HTTP 400 because it could not find
the entity end, leaving the hackathon correctly unarchived but undelivered.

## Decision

Continue escaping untrusted text, but render description bodies as plain text after the `📝`
label. Keep Markdown only for fixed labels and the application link, whose structure the bot owns.

## Alternatives considered

- **Add more legacy Markdown escaping:** fragile because provider text can combine punctuation,
  handles, URLs, and entity boundaries in new ways.
- **Move everything to MarkdownV2:** requires a broader escaping migration across every field and
  link, increasing regression surface for no product benefit.
- **Use HTML parse mode:** workable, but still requires an all-field escaping migration.

## Consequences

Descriptions are no longer italic, but malformed provider text cannot break their enclosing entity.
Fixed labels and links retain the existing visual hierarchy.

## Reversal condition

Revisit if the entire formatter migrates to a structured entity API or a fully tested HTML or
MarkdownV2 renderer.
