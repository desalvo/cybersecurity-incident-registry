# RC10 CI triage

GitHub Actions log archive: logs_122036530141.zip (user supplied, not bundled).

14 pytest failures, 934 passed, 24 skipped, 179 subtests passed.
Browser: Broken visible image on documentation-admin-desktop.

Local tests: 18/18 originally failing parameterized cases passed after changes; 144 additional tests and 51 subtests passed. Full suite timed out; browser could not navigate loopback in this environment (ERR_BLOCKED_BY_ADMINISTRATOR). The browser assertion now includes URLs to make the next CI failure actionable.

This release is a candidate only.
