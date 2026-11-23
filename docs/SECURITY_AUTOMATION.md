# Continuous CIR security checks

The permanent **CIR security-only diagnostic** workflow accepts `[ci-security]` in the last commit message of a development push or PR, or a manual dispatch. It builds amd64 and arm64 images locally, scans both with Trivy, retains raw JSON artifacts, and **never pushes or promotes images**. On Wednesdays at 06:45 UTC it also runs automatically against `main`, independent of commit markers.

The existing **CIR periodic security review** runs Mondays at 06:15 UTC on `main` and checks Python dependencies and the recorded immutable production digest on both platforms. If the digest is still pending, that review fails intentionally; the Wednesday source-image scan nevertheless gives current-source vulnerability visibility.

Both scheduled review workflows create or update a dedicated GitHub Issue on failures and close it when their respective review succeeds. Issues link to the exact Actions run and evidence. Repository Actions permissions must allow `GITHUB_TOKEN` to write Issues for these jobs; a policy restriction causes a visible notification job failure, not silent success. No email, webhook or third-party service is required; subscribe to repository Issues notifications to receive alerts.

Security-only results **never replace** required full PR checks or production approval. Scheduled scans do not change `TRIVY_RISK_ACCEPTANCE_R8.json`, and the expired disposition remains blocking. Manual dispatch of the periodic production review also generates an issue when a review fails.
