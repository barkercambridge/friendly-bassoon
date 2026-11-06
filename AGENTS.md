# Virtual Admin — development instructions

Environment: Windows. Active DevStan is maintained in private `barkercambridge/miniature-memory` at the exact approved commit in `config/central-standards.json`. Preflight and Release retrieve and integrity-check its `docs/development-standard.md`, `docs/python-defect-register.md` and `docs/development-defect-register.md` into their ephemeral workspaces before existing checks. `docs/development-standard.md` is a validated runtime copy, not an independently editable repository-local standard. The local `docs/document-register.json` remains the Virtual Admin application inventory; the central repository has its own register. Never bypass failed retrieval or substitute a newer central commit without explicit approval.

Preserve numbered functional requirements (FR-###), acceptance tests (AT-###), `traceability.json` mappings, and original acceptance evidence. Planned FRs may have no test mapping; implemented FRs must map to applicable acceptance tests. Never treat an unexecuted acceptance test as PASS.

Require explicit owner approval before source-code commits or Devstan revisions. Production publication is governed by automated, attributable approval only after passing acceptance evidence, source/package equivalence and all mandatory Devstan gates; automated approval does not imply personal owner approval. `NOT VERIFIED` blocks production. Do not commit secrets.

Commit approved changes directly to `main` by default; create a branch or pull request only when explicitly requested or required by repository protection. Preserve historical Git records without treating obsolete external standards as active dependencies.
