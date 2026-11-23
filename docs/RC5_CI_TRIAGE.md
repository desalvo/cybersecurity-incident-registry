# CIR 0.10.0-1 RC5 - CI triage

Baseline: RC4, confirmed committed by the maintainer. The attached CI log archive
`logs_122017006047.zip` reports 928 passed, 20 failed, 24 skipped and
179 subtests passed in the complete pytest suite. The UI documentation job
failed at pip-audit for Werkzeug 3.1.8; the log identifies 3.1.9 as the fix.

This candidate updates Werkzeug to 3.1.9 and the pinned-version invariant.
It is NOT a resolution of the 20 functional regressions. Do not merge or
promote this package as a green-CI fix without rerunning all required checks.

Outstanding groups: tenant defaults and full import, wizard, UI/AlBot,
PDF structure, release metadata, external recipients and workflow catalog.
Some failures are test expectations, while others may be genuine defects;
no test was weakened or disabled in this candidate.

Local environment does not have Flask or access to install packages, so the
full HTTP/SQLAlchemy suite and pip-audit could not be rerun. The exact
published artifact needs CI validation with its pinned dependencies.
