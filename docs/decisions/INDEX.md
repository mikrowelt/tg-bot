# Architecture Decision Records

Log of significant design decisions for tg-bot.

## ADR Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [ADR-001](ADR-001-mixin-composition.md) | Mixin Composition for Client | Accepted | 2024-01 |
| [ADR-002](ADR-002-subprocess-workers.md) | Subprocess Worker Isolation | Accepted | 2024-01 |
| [ADR-003](ADR-003-error-classification.md) | Error Classification Strategy | Accepted | 2024-01 |
| [ADR-004](ADR-004-verification-caching.md) | Verification Pattern Caching | Accepted | 2024-01 |
| [ADR-005](ADR-005-pydantic-config.md) | Pydantic for Configuration | Accepted | 2024-01 |

## ADR Template

```markdown
# ADR-XXX: Title

## Status
Proposed | Accepted | Deprecated | Superseded

## Context
What is the issue that we're seeing that is motivating this decision?

## Decision
What is the change that we're proposing?

## Consequences
What becomes easier or more difficult to do because of this change?
```

## Decision Principles

1. **Explicit over implicit** — Configuration and behavior should be clear
2. **Isolation over sharing** — Prefer subprocess isolation to shared state
3. **Retryable errors** — Distinguish temporary from permanent failures
4. **Human-like timing** — Use random delays to avoid detection
5. **Cache with care** — Only cache patterns with good success rates
