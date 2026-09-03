# Security update - Release Candidate R4

Release: `0.9.0-1`  
Build: `20260902`

## Reason for R4

The live `pip-audit` run performed after RC R3 found known vulnerabilities in two directly pinned dependencies:

- `pypdf==6.10.2`, including denial-of-service conditions fixed across later 6.x releases;
- `cryptography==46.0.7`, including certificate-verification/resource-exhaustion issues and a PKCS#7 decryption oracle fixed in later releases.

RC R4 updates only these direct runtime pins:

- `pypdf==6.16.2`
- `cryptography==50.0.1`

No application feature or database-schema change is introduced by R4.

## Required production revalidation

Because dependency binaries changed, the production gate must be rerun in a network-enabled environment using the exact R4 requirements. Promotion requires:

1. `python -m pip check`
2. `python -m pytest -q`
3. `./scripts/run_postgres_tests.sh`
4. `python scripts/verify_release_candidate.py`
5. `./scripts/run_sca.sh` with no unresolved vulnerability in the release environment
6. multi-architecture image build and final container-image scan
7. immutable registry digest promotion

The analysis environment used to assemble R4 cannot download the new wheels, so it does not claim binary-level regression or a post-update live SCA result. Those checks must be performed on the release host before production promotion.
