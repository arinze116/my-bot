# ADR-0003: Group X discovery terms and reject noise locally

- Date: 2026-11-16 Africa/Lagos
- Status: superseded by ADR-0005
- Rule ids affected: R-DISCOVERY-1, R-TIMEOUT-1

## Context

The owner supplied a broader discovery lexicon spanning core hackathon terms, calls to action,
Web3 ecosystems, regional and niche events, listing platforms, and explicit noise phrases. One
request per keyword would require dozens of X calls every 20 minutes, while one broad `hackathon`
query would let high-volume recap and winner posts consume the 100-result response cap.

## Decision

Use eight Boolean query groups, each no longer than 512 characters and each excluding retweets and
non-English posts. Group related terms so one poll uses eight X calls. Reject the owner's explicit
noise phrases and term pairs locally before normalization, deduplication, or Telegram delivery.
An observed active-participant "Day 1" diary pattern is also rejected because it is not a new
registration opportunity.
Keep `TWITTER_QUERIES` as a complete custom override; an empty value selects the built-ins.

## Alternatives considered

- **One query per keyword:** clearest mapping, but needlessly multiplies API reads and rate-limit
  exposure.
- **One broad query:** cheapest call count, but likely loses niche announcements behind high-volume
  generic chatter and the response cap.
- **Only negative query operators:** saves local filtering, but repeats a long exclusion suffix in
  every query and is harder to test against punctuation and phrasing variations.

## Consequences

The requested vocabulary is testable in source control and the call count remains bounded. Local
filtering may reject a genuine event post that also advertises a course or bootcamp. X relevance,
recency, entitlement, and response limits still prevent a guarantee of complete discovery.

## Reversal condition

Revisit grouping if X changes query limits or billing, if measured result saturation causes missed
events, or if false-positive/false-negative evidence justifies a scored classifier.
