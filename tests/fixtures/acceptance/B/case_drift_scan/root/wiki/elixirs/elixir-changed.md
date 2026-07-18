---
id: elixir-changed
protocol: general
citations:
  - "raw/evidence.md"
  - "raw/missing.md"
citation_snapshots:
  - "raw/evidence.md#deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
  - "raw/missing.md#cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe"
---

# Elixir with drifted + stale citation snapshots

Seeded for B acceptance fixture: `raw/evidence.md` exists on disk with a
different SHA-256 than the recorded snapshot (→ drifted), and `raw/missing.md`
is listed in both `citations` and `citation_snapshots` but absent on disk so
`evidence_path_digest` returns "" and it never makes it into `current` —
ending up in `stale_paths` strictly because the file is missing, not because
the citation was dropped.
