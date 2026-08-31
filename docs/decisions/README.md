# Spektrafilm Architecture Decisions

| Field | Value |
| --- | --- |
| Status | Canonical process |
| Purpose | Preserve durable architectural rationale without turning current-state docs into history logs |

Architecture Decision Records (ADRs) capture choices that future contributors or agents are likely to reconsider. They are not implementation reports and should stay much shorter than the research that informed them.

## When to add an ADR

Add one when a change does one or more of the following:

- moves a semantic ownership boundary;
- creates or removes a source of truth;
- changes package dependency direction;
- changes a durable exactness/compatibility contract;
- introduces a persistent data/provenance policy;
- deliberately rejects an attractive alternative for a reason future work might otherwise rediscover;
- changes how branch/report knowledge is promoted into the canonical system.

Do not add ADRs for ordinary bug fixes, isolated implementation details, or benchmark results with no durable architectural consequence.

## Lifecycle

Use these statuses:

- `Proposed` — under review; not yet authoritative.
- `Accepted` — current decision.
- `Superseded` — replaced by another ADR; keep the file and link to the replacement.
- `Rejected` — considered but intentionally not adopted; retain when the rationale has future value.

Accepted decisions are historical rationale. If the system changes, add a superseding ADR rather than rewriting the old decision so extensively that its original context disappears.

## Minimal ADR shape

```markdown
# NNNN — Decision title

Status: Accepted
Date: YYYY-MM-DD
Scope: <layers/subsystems>
Supersedes: <ADR or none>
Superseded by: <ADR or none>

## Context
<problem and constraints>

## Decision
<what is now true>

## Invariants
<what this decision protects>

## Consequences
<benefits, costs, migration implications>

## Alternatives considered
<only alternatives with durable learning value>

## Evidence
<links to reports/tests/PRs; evidence is not duplicated here>

## Revisit when
<conditions that invalidate the premises>
```

## Index

- [`0001-agent-operable-architecture.md`](0001-agent-operable-architecture.md) — use a small canonical control plane, explicit evidence vocabulary, and knowledge promotion instead of branch/report archaeology as the primary way to understand the repository.
