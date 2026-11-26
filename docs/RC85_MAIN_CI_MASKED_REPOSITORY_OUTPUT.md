# CIR 0.10.0-1 RC85 — fix post-merge CI documentation publication

## Evidence and exact failure

The user-supplied GitHub Actions archive `logs_123761556845.zip` is from
run `45742492679` on `main`, source commit
`c2e6de0f1c91812db604cba83ecfa3d29c7ccb69`, 2026-11-26.

* `Tests, PostgreSQL, SCA and offline gates`: **1,157 passed, 34 skipped,
  188 subtests passed**. This is not a test failure.
* `Real UI screenshots and documentation`: **PASS (16 verified artifacts)**;
  the same-run artifact was uploaded and downloaded by the publisher.
* `Build, scan and promote multi-arch image`: successfully published the
  immutable digest `sha256:d980c2c62c664df72206693ea3f84c0eb9879af736138e6bbbb20303e07bcccf`.
  At job teardown GitHub printed **`Skip output 'repository' since it may
  contain secret.`** and exported only the `digest` output.
* `Publish only current verified screenshots and training documents`: failed
  before staging files or opening its PR. It received a nonempty promoted
  digest but an empty `PUBLISHED_REPOSITORY`, so
  `scripts/record_production_digest.py` correctly rejected `''` with exit 2.
* `Enforce documentation publication result on main`: correctly failed in
  response to the unsuccessful publication job.

The release repository name contains the Docker Hub account name, which is
also present in an Actions secret. GitHub's job-output secret detector can
therefore suppress the repository output even though the repository itself is
public. This is an Actions output handling issue, not evidence of a missing
Docker release, broken screenshot capture, or missing documentation artifacts.

## RC85 implementation

1. `docker-release` exports **only** the verified immutable digest; do not
   attempt to transmit the repository name through a potentially redacted job
   output. The Docker release job continues to derive its own repository from
   the configured `CIR_DOCKER_REPOSITORY` repository variable or the shared
   default `DEFAULT_DOCKER_REPOSITORY`.
2. The publication job resolves the repository locally using **the same
   configuration expression**. It is deliberately never exported through
   `GITHUB_OUTPUT`, re-encoded, or bypassed around GitHub masking.
3. The publication shell contract now checks the result explicitly:
   * `success`: digest must be present, then call strict
     `record_production_digest.py` and verify generated metadata;
   * `skipped`: digest must be absent (documentation-only rebuild);
   * any other state: fail closed rather than silently publish incomplete
     production metadata.
4. New regression tests execute the actual GitHub workflow publication-shell
   prefix in isolated temporary directories. They verify the default and
   customized repository, correct image pinning, no rewrite for a skipped
   Docker job, and rejection of missing, malformed or contradictory metadata.

No application runtime, presentations, browser screenshots, or generated
manual/brochure binaries were changed by this RC. The rebuilt documentation
must come from the next authenticated CI run of the actual source commit.

## Local validation

`python -m pytest -q tests/test_rc85_masked_docker_repository_output.py
 tests/test_rc82_documentation_publication.py
 tests/test_rc83_training_focus_and_pr_accountability.py
 tests/test_documentation_publication_rc73.py
 tests/test_hotfix7_structure_ci_and_gate.py`

Result: **49 passed**. Additional local checks cover YAML parsing, patch
applicability and equivalence of patched source with packaged deltas.

## Merge/recovery workflow

Apply the RC85 patch on top of the confirmed RC84 merge in a new pull request;
require green PR CI, then merge to `main`. A rerun of the old failed run alone
still executes the old workflow and does **not** repair the configuration.

On the *new* `main` run, confirm that Docker promotion completes (when the
source change policy requires an image), that the publisher records the digest
without reading `needs.docker-release.outputs.repository`, stages the freshly
verified same-run documentation, and opens a documentation PR. The
`documentation-publication-accountability` job must report `pr-opened` or
`already-current`. Review and merge the generated documentation PR according
to normal protected-branch policy.

An optional `workflow_dispatch` on the fixed `main` can rebuild documents
without Docker, but that documentation-only path intentionally does not record
a **newly promoted** digest. Use the normal fixed source-change CI to ensure
production digest metadata is synchronized.

The provided logs show successful document generation and failed publication;
**no remote rerun or PR creation is claimed by RC85**.
