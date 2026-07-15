# Acceptance Golden Slimdown Strategy

## Goal

Keep acceptance tests as behavior gates while reducing repeated full-file
golden churn. The current fixture shape is still the source of truth until a
case is migrated deliberately.

## Strategy

1. **Shared base fixtures**
   - Move repeated vault scaffolding into a shared base per milestone or feature
     family.
   - Let each case provide only the input delta and behavior-specific expected
     artifacts.
   - Keep provenance-bearing files explicit when they are the behavior under
     test.

2. **Field assertions over full snapshots**
   - For JSONL receipts, run logs, and shell summaries, assert stable fields:
     `status`, `event`, `backend_effective`, `delivery_mode`, target paths,
     receipt IDs, and failure classification.
   - Ignore generated timestamps, ordering noise that is not user-visible, and
     large unchanged nested sections unless the case is specifically about
     serialization stability.

3. **Pilot candidates**
   - Start with one backend-failure or run-log case where many lines repeat the
     same receipt envelope and only a few fields carry the regression risk.
   - Avoid protocol/template cases first; those are more likely to need
     full-text markdown review.

## Risks

- Over-slimming can hide markdown regressions that only appear in surrounding
  context.
- Shared bases can make a failing case harder to read if the base becomes too
  broad.
- Receipt/audit fields are product-critical; any field assertion list must stay
  explicit and reviewed.

## Exit criteria for a migrated case

- The test failure message points to the behavior field that drifted.
- A reviewer can reconstruct the full materialized output locally.
- Acceptance still catches missing receipt/audit/provenance writes.
