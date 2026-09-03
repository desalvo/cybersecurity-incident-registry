# Security Audit Round 18 - Release Candidate

Release lineage: baseline `0.8.0`; Rounds 1-18 are internal development/audit iterations of functional release `0.9.0-1`, not separate 0.8.x releases.

Scope: final release consistency, release metadata, packaging integrity, deployment policy checks, SBOM refresh, and explicit separation of offline versus infrastructure-dependent production gates.

## Confirmed finding and remediation

### MEDIUM - Release build metadata no longer represented the hardened source state

The project still declared build `20260718` even though the hardened source had advanced through security rounds completed on 2026-09-02. This made runtime/UI/deployment metadata stale and weakened traceability between a deployed artifact and the reviewed source.

Round 18 finalizes release-candidate metadata at build `20260902` for functional release `0.9.0-1`, which cumulatively contains the work developed throughout Rounds 1-18 from the 0.8.0 baseline. Docker Compose, Kubernetes, README files, SBOM metadata and release tests are synchronized with the release candidate.

## Release-candidate gate

`scripts/verify_release_candidate.py` now checks source-tree invariants that must not drift between releases: VERSION/BUILD synchronization, immutable-style Kubernetes tagging (no `:latest`), production Compose and Kubernetes hardening controls, sensitive packaging exclusions, and CycloneDX SBOM consistency. It can additionally validate the syntax of a final `image@sha256:` production reference.

The release packaging script writes a SHA-256 sidecar for the generated ZIP so the artifact can be verified independently after transfer.

`SBOM_ROUND18.cdx.json` refreshes the transitive Python inventory for the RC from the supplied offline wheel environment. Dependencies are unchanged from Round 17.

## External gates intentionally not claimed as complete

The RC remains conditional until a network-enabled SCA run, the seven real-PostgreSQL integration tests, a scanner run against the exact final container image, and immutable registry digest promotion are completed. These requirements are documented in `RELEASE_CANDIDATE_ROUND18.md` and are not represented as passing when the required infrastructure is unavailable.

## Verification

- Full standard pytest suite: **292 passed, 7 skipped, 0 failed**. The seven skips are the opt-in real-PostgreSQL tests because Docker/PostgreSQL is not available in this analysis environment.
- Round 18 targeted release/packaging tests: PASS.
- `scripts/verify_release_candidate.py`: PASS.
- Offline CycloneDX SBOM refresh: PASS, 47 Python components.
- `pip check` in the isolated exact-wheel environment: PASS.
- `python -m compileall` for application/tests/scripts: PASS.
- Shell syntax checks using each script's declared interpreter: PASS.
- Docker Compose and Kubernetes YAML parsing: PASS.
- Docker daemon availability in this environment: unavailable; therefore real PostgreSQL/container-image gates remain pending by design.
