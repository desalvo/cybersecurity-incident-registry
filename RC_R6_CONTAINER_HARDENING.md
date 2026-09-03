# RC R6 - Container hardening

Release lineage: baseline 0.8.0 -> cumulative release 0.9.0-1. RC R6 changes only the container build/runtime packaging.

## Why

Trivy reported the old `cryptography 46.0.7` and `pypdf 6.10.2` even though the R5 requirements pin 50.0.1 and 6.16.2. The image copied historical CycloneDX files (notably Round 6/17 SBOMs), and Trivy explicitly warned that third-party SBOMs were being consumed. Those historical artifacts are source/release documentation and are not runtime dependencies.

The Debian scan also showed a broad dependency surface from GUI LibreOffice packages and curl. CIR uses LibreOffice only for headless Writer conversion.

## Changes

- `.dockerignore` excludes historical SBOMs, audit/release/migration markdown, pytest artifacts and tests from the runtime image. These files remain in the downloadable source ZIP.
- Docker runtime uses `libreoffice-writer-nogui` instead of `libreoffice-writer` + `libreoffice-core`.
- `curl` is removed; the Docker HEALTHCHECK uses Python `http.client`.
- `apt-get upgrade -y` is run before runtime packages are installed so available Debian security updates are incorporated.

## Required external validation

Rebuild with `--pull --no-cache` (supported by the R6 build script) and rerun Trivy. Residual Debian findings with no stable fixed version must be assessed against Debian Security Tracker and actual runtime reachability; they are not silently ignored.
