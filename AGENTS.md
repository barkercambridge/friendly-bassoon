# Virtual Admin — development instructions

Environment: Windows. Active Development Standards is maintained in private `barkercambridge/miniature-memory` at the exact approved commit in `app-repo:config/central-standards.json`. Preflight and Release retrieve and integrity-check its `standards-repo:docs/development-standards.md`, `standards-repo:docs/python-defect-register.md` and `standards-repo:docs/development-defect-register.md` into their ephemeral workspaces before existing checks. `standards-repo:docs/development-standards.md` is a validated runtime copy, not an independently editable repository-local standard. The local `app-repo:docs/document-register.json` remains the Virtual Admin application inventory; the central repository has `standards-repo:docs/development-standards-register.json` as its separate register. Never bypass failed retrieval or substitute a newer central commit without explicit approval.

Preserve numbered functional requirements (FR-###), acceptance tests (AT-###), `app-repo:config/traceability.json` mappings, and original acceptance evidence. Planned FRs may have no test mapping; implemented FRs must map to applicable acceptance tests. Never treat an unexecuted acceptance test as PASS.

Require explicit owner approval before source-code commits or Development Standards revisions. Production publication is governed by automated, attributable approval only after passing acceptance evidence, source/package equivalence and all mandatory Development Standards gates; automated approval does not imply personal owner approval. `NOT VERIFIED` blocks production. Do not commit secrets.

Commit approved changes directly to `main` by default; create a branch or pull request only when explicitly requested or required by repository protection. Preserve historical Git records without treating obsolete external standards as active dependencies.

The Functional Specification is authoritative at `app-repo:docs/functional-specification.md`. Repository-file references in application documents must use `app-repo:` or `standards-repo:`; these documentation prefixes are not filesystem paths.
