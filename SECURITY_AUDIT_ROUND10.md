# Security / Regression Round 10

Release lineage: baseline `0.8.0`; this round is an internal development/audit iteration of functional release `0.9.0-1`, not a standalone 0.8.x release.

Scope: elimination of the remaining SQLAlchemy legacy warnings from Round 9, warning-regression prevention, and verification that the change does not alter application behavior.

## Findings and remediation

### LOW - Test suite still used SQLAlchemy 1.x `Query.get()`

Round 9 completed with 245 passing tests and 8 `LegacyAPIWarning` messages. All eight warnings came from test assertions that still used `Setting.query.get(primary_key)`, which SQLAlchemy 2.x marks as legacy.

Round 10 replaces those test-only lookups with `db.session.get(Setting, primary_key)`. This is the SQLAlchemy 2.x primary-key lookup API and preserves the same test semantics without modifying application behavior.

### LOW - Legacy API warnings were not promoted to test failures

A future `Query.get()` regression could previously be merged while leaving the suite green and only emitting a warning.

Round 10 configures pytest to treat `sqlalchemy.exc.LegacyAPIWarning` as an error. A static regression test also scans Python sources under `app`, `tests`, and `scripts` and fails if a direct `.query.get(` call is introduced.

## Dependency-owned warnings

When Python is explicitly run with broad warning display (`-W default`), additional deprecation messages can originate inside third-party packages (notably ldap3/pyasn1 and matplotlib/pyparsing), and Python 3.13 may report SQLite resource warnings during aggressive warning diagnostics. The normal project pytest configuration already scopes known dependency deprecations, while Round 10 eliminates all project-owned SQLAlchemy legacy warnings. No dependency versions were changed in this round to avoid functional risk unrelated to the requested cleanup.

## Verification

- `python -m compileall -q app tests scripts`: PASS
- `sh -n docker-entrypoint.sh`: PASS
- Full `pytest -q`: **246 passed, 0 warnings**
- `LegacyAPIWarning` is configured as a pytest error: PASS
- Static no-`Query.get()` regression invariant: PASS

## Next priorities

1. Run PostgreSQL-backed integration tests for transactional restore, advisory locking, rollback, and sequence alignment under real concurrency.
2. Generate a complete transitive SBOM/SCA report in CI from the resolved dependency environment.
3. Review third-party dependency deprecations during the next safe dependency-maintenance cycle rather than suppressing or patching vendor code locally.
4. Continue auditing restored/persistent metadata at filesystem, URL, and command boundaries.
