# RC24 — Security CI invocation correction

The GitHub Actions run 45216896624 failed on amd64 and arm64 with exit code 126: `./scripts/run_trivy_production_gate.sh: Permission denied`. Both Debian inventories were complete but the Trivy diagnostic summaries had `reports: []`. Therefore that run provides **no new vulnerability scan**.

The fast PR workflow, production release workflow and scheduled production review now invoke `bash ./scripts/run_trivy_production_gate.sh` rather than executing the file directly. The ZIP member is also marked executable. **Git tracks its own executable bit**, so the person committing this package should additionally run `git update-index --chmod=+x scripts/run_trivy_production_gate.sh` and check `git diff --summary` before committing. No risk policy, allowlist or application functionality is changed.

Run `[ci-security]` on the branch to verify both scans generate real JSON reports. Do not infer CVE status from the empty summary of the failed run. Production promotion remains blocked pending valid security evidence and approved risk disposition.
