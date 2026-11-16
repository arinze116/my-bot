# ADR-0005: Require high-signal X hackathon announcements

- Date: 2026-11-17 Africa/Lagos
- Status: accepted
- Supersedes: ADR-0003
- Rule ids affected: R-DISCOVERY-1

## Context

The broader eight-query rollout found relevant events but also passed personal experience posts,
recaps, and general hackathon mentions. Those false positives produced noisy Telegram alerts and
consumed more X results than the listing use case needed.

## Decision

Use the owner's seven registration/deadline/prize-oriented queries. Before normalization, require
`is_announcement(tweet_text)` to find at least one announcement signal word. Reject retweets,
explicit first-person recap phrases, and the existing course, bootcamp, hiring, and participant
diary noise patterns. Live smoke review also rejects first-person `I was` experience narratives
that happen to quote submission or deadline language.

## Alternatives considered

- **Keep broad queries and expand only the blocklist:** preserves recall but requires endless
  reactive phrase additions and still spends reads on low-signal results.
- **Use a classifier:** potentially more nuanced, but adds cost, latency, training/evaluation work,
  and an external failure mode for a deterministic personal bot.

## Consequences

X volume and false positives decrease. Announcements that omit every configured signal word can be
missed; that precision-over-recall tradeoff is explicit and covered by deterministic tests.

## Reversal condition

Revisit if measured false negatives show that important announcements systematically omit the
signal vocabulary, or if a labelled evaluation set justifies a classifier.
