# RC81 - CI provenance and documentation evidence recovery

This release candidate fixes failures introduced by the tenant notification
inheritance and authenticated UI documentation updates, without weakening the
security gates or changing operational notification inheritance semantics.

## Corrections

* Full backup archive validation accepts the two explicitly recognized
  same-tenant notification override markers. Marker values must be the boolean
  `true`, must match the referenced local resource type and the name/code of
  the shared source, and must belong to the referenced tenant. Foreign or
  forged provenance remains rejected.
* The Wizard desktop and panel screenshots are verified as real authenticated
  element captures with the correct route, selector, dimensions and SHA-256.
  Only actual online documentation landing pages require full first-viewport
  screenshots.
* Documentation tests distinguish the last frozen editable-source presentation
  from the version produced by the CI for the current source digest. CI
  publication still requires new real screenshots and current receipts.
* Pre-existing legacy tests now check the requested same-code tenant override
  semantics instead of expecting obsolete `_td` duplicate codes.
* Tests referencing prior navigation wording and slide numbers were adjusted to
  the current presentation layout and tenant Wizard navigation.

## Verification

Run the complete CI with pinned dependencies and live browser/PostgreSQL jobs.
The offline compatibility test environment uses the user-supplied
`cir-python-wheels.zip` for Python 3.13 (including Flask 3.1.3,
Flask-SQLAlchemy 3.1.1 and psycopg2-binary 2.9.10). The user wheel archive has
older versions of some dependencies than `requirements.txt`; this is a
compatibility test rather than the exact pinned deployment environment.

Python 3.13 example (offline):

```sh
python -m venv /tmp/cir-rc81-venv
/tmp/cir-rc81-venv/bin/pip install --no-index --find-links /path/to/wheels \
  Flask==3.1.3 Flask-SQLAlchemy==3.1.1 Flask-Login==0.6.3 psycopg2-binary==2.9.10
/tmp/cir-rc81-venv/bin/python -m pytest -q
```

The CI must be rerun for release qualification; the local compatibility suite
cannot attest remote PostgreSQL, browsers, documentation publishing or SCA.
