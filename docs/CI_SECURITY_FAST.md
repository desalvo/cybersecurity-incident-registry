# Temporary `[ci-security]` workflow

Add the literal `[ci-security]` to the **latest commit message** on a feature branch, including a branch used by a pull request. GitHub Actions will run `CIR security-only diagnostic (temporary)` and skip the expensive full CI jobs for that **non-main** ref. The separate diagnostic workflow builds local, unpromoted amd64/arm64 images and runs the existing Trivy policy gate on each, uploading both raw JSON reports even on failure. `workflow_dispatch` can also launch this diagnostic workflow manually.

Example: `git commit -m "chore(cir): inspect runtime vulnerabilities [ci-security]"` then push. If the PR uses a merge ref, the selector explicitly fetches the PR head SHA to inspect the real latest commit message.

**Safety boundaries:** The marker never skips full CI on `main` or tag pushes. The diagnostic does not publish to Docker Hub, update a digest, renew risk acceptance or promote an image. A Trivy policy failure remains a failure. A green diagnostic does **not** authorize merge or production. Before merging, push a subsequent commit **without** `[ci-security]` to rerun the full CI on the PR and satisfy required checks. Protect the main branch with the normal full-quality required checks; the temporary selector itself must not be treated as equivalent evidence. GitHub may show previously required checks as skipped in the fast run; repository rulesets must require a fresh full run before merge. If the branch protection accepts skipped required checks as success, disable this temporary mode and use the full CI before merging.

For normal operation, remove the `[ci-security]` marker from new commits. To remove this temporary feature permanently, delete `.github/workflows/ci-security-fast.yml`, the `ci-mode` job and its `needs`/`if` guards in `.github/workflows/ci-release.yml`.

The two image builds are still substantial because LibreOffice is part of the runtime. They avoid the full pytest/PostgreSQL/browser documentation jobs but are not instant. If security policy is expired, both scans should fail until the residual-risk assessment is properly updated; the scans remain useful as diagnostic evidence.

The diagnostic Docker build sets `CIR_SECURITY_DIAGNOSTIC=1`, which omits the **documentation provenance check only** because the screenshot bundle is normally created by the expensive UI job. The production Docker build leaves this argument at its secure default `0` and still requires the verified bundle. No application dependencies or Debian packages are changed by this switch.
