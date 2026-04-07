# Runtime Schema

This directory contains runtime policy for `aiwiki`.

It is product-facing policy, not developer governance.

## Core Policy Files

- [Ingest Rules](./ingest.md)
- [Citation Rules](./citations.md)
- [Conflict Rules](./conflicts.md)
- [Review Rules](./review.md)
- [Writeback Rules](./writeback.md)
- [Taxonomy Rules](./taxonomy.md)

## Boundary

- `AGENTS.md` and `CLAUDE.md` are repository/developer files.
- Runtime behavior should be driven by this directory plus `prompts/`.
