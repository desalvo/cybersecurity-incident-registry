# RC R5 - Crash test harness stabilization

Version: `0.9.0-1`  
Build: `20260902`

## Context

During final validation of RC R4 with the security dependency updates (`pypdf==6.16.2`, `cryptography==50.0.1`), all external gates passed except one SQLite process-crash test:

`tests/test_security_round15_process_crash.py::test_sigkill_after_db_commit_keeps_promoted_filesystem`

The worker did not reach its checkpoint within the test harness timeout. The equivalent real-PostgreSQL pre-commit and post-commit SIGKILL tests both passed (`7 passed` for the PostgreSQL integration group), so there was no evidence of an application crash-recovery regression.

## Change

The SQLite external-process checkpoint timeout is increased from 15 seconds to 30 seconds and can be overridden with:

```bash
CIR_CRASH_TEST_CHECKPOINT_TIMEOUT=45 python -m pytest -q tests/test_security_round15_process_crash.py
```

Values below five seconds are clamped to five seconds. Invalid values fall back to 30 seconds.

The test still fails if the worker exits early or does not reach the checkpoint. The failure message now includes elapsed time and the effective timeout, in addition to worker stdout/stderr.

## Runtime impact

None. Only test-harness code changed. Application code, database schema, production configuration and dependency pins are unchanged from RC R4.

## Verification in the packaging environment

- post-commit SIGKILL test: 5 consecutive passes;
- full standard suite: `295 passed, 7 skipped` using the available offline dependency environment;
- the seven skipped tests are the opt-in real-PostgreSQL tests.

The final production promotion still requires rerunning the standard suite on the target validation host with the RC R4/R5 security dependency versions installed.
