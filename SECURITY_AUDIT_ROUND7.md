# Security Audit Round 7

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: filesystem trust boundaries for database-backed uploads, legacy/corrupted metadata resilience, document/attachment download and deletion, and Alfresco local-file handoff.

## Confirmed finding and remediation

### HIGH - Database-backed `stored_name` values reached filesystem operations without revalidation

Document and action-attachment paths were reconstructed with `os.path.join(UPLOAD_DIR, stored_name)` at download, delete, and Alfresco-upload boundaries. New uploads and Round 6 imports already generate/validate safe opaque names, but existing database rows are a separate trust boundary: a legacy, manually altered, or otherwise corrupted `stored_name` containing an absolute path or traversal components could make those operations address a file outside the managed upload directory.

Round 7 adds `safe_upload_path()`, which requires the stored value to be an unchanged `secure_filename()` basename, resolves the configured upload directory and candidate path, verifies the candidate remains a direct child of that directory, and (for reads/deletes) requires an existing regular file. Document downloads, action-attachment downloads, their deletion paths, and the Alfresco local-file handoff now use this helper.

This is defense in depth: archive validation from Round 6 remains in place, while the filesystem boundary no longer assumes that historical database content is trustworthy.

## Verification

- `python -m compileall -q app tests`: PASS.
- `pytest -q tests/test_security_round6_invariants.py tests/test_security_round7_invariants.py`: PASS.
- Static Round 7 regression tests verify path canonicalization and coverage of document/attachment download, deletion, and Alfresco handoff.

## Residual risk / next priorities

1. Replace remaining direct `UPLOAD_DIR` path construction with centralized helpers where the filename can originate from persistent metadata.
2. Add integration tests with PostgreSQL and real multi-worker restore/backup execution.
3. Run full dependency/SCA scanning in the network-enabled CI image and generate a transitive SBOM.
4. Continue reducing raw exception text exposed by non-network administrative/UI workflows where unexpected exceptions may contain implementation details.
