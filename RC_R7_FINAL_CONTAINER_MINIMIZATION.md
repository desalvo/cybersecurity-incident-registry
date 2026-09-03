# RC R7 - Final container minimization

Release lineage: **0.8.0 baseline -> 0.9.0-1 release candidate**. R7 is a packaging/container-hardening iteration of 0.9.0-1 and does not change application functionality.

## Why R7 was required

The R6 Trivy scan no longer reported the historical pypdf/cryptography findings, but still reported two Python HIGH findings for `msgpack 1.1.2` and `setuptools 70.3.0`. Those versions originate from the CycloneDX document embedded in pip (`pip/_vendor/bom.cdx.json`), not from CIR runtime requirements. The same scan still reported Debian HIGH/CRITICAL findings in libraries pulled by the Python/Debian base and the headless LibreOffice conversion stack.

## Changes

- Dockerfile converted to a two-stage build.
- Python application dependencies are installed into `/opt/cir-venv` in the `python-deps` stage.
- `pip`, `setuptools`, and `wheel` are removed from the application venv after installation.
- The runtime stage removes the packaging tooling shipped by the official Python base image as well, including pip's embedded third-party SBOM that can be interpreted by vulnerability scanners as installed packages.
- Runtime still installs only `ca-certificates`, `gosu`, `fonts-dejavu-core`, and `libreoffice-writer-nogui` with `--no-install-recommends`.
- No Debian package metadata is deleted or hidden. Full Trivy OS results remain visible and must be evaluated against Debian's security tracker/upstream patch availability.

## Production validation

Build from a clean/pulled base (the multi-arch script does this by default):

```bash
./scripts/build_multiarch_image.sh --repository desalvo/cybersecurity-incident-registry --tag 0.9.0-r7
```

Confirm application dependency versions:

```bash
docker run --rm desalvo/cybersecurity-incident-registry:0.9.0-r7 \
  python -c "import pypdf, cryptography; print(pypdf.__version__, cryptography.__version__)"
```

Confirm packaging tools are absent from runtime:

```bash
docker run --rm --entrypoint sh desalvo/cybersecurity-incident-registry:0.9.0-r7 -c \
  'command -v pip && exit 1 || true; python -c "import importlib.util; assert importlib.util.find_spec(\"setuptools\") is None"'
```

Run and retain the full scan:

```bash
trivy image --severity HIGH,CRITICAL --format json --output TRIVY_R7.json \
  desalvo/cybersecurity-incident-registry:0.9.0-r7
trivy image --severity HIGH,CRITICAL desalvo/cybersecurity-incident-registry:0.9.0-r7
```

The primary gate remains the **full** report; do not delete Debian package metadata and do not treat `--ignore-unfixed` as proof that the image is vulnerability-free.
