"""Release identity shared by source packaging, CI, documentation and runtime.

VERSION is the functional release. BUILD is generated once per build operation
in Europe/Rome (YYYYMMDD) and baked into the resulting files/image; it never
changes merely because the application restarts. Existing files are authoritative
and cannot be shadowed by legacy deployment APP_VERSION/APP_BUILD variables.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Mapping
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
BUILD_TIMEZONE = "Europe/Rome"
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?")
_BUILD = re.compile(r"[0-9]{8}")


@dataclass(frozen=True)
class ReleaseMetadata:
    version: str
    build: str

    def as_dict(self) -> dict[str, str]:
        return {"version": self.version, "build": self.build}


def validate_version(value: str) -> str:
    if not isinstance(value, str) or not _VERSION.fullmatch(value):
        raise ValueError("VERSION must be a valid functional release identifier")
    return value


def validate_build(value: str) -> str:
    if not isinstance(value, str) or not _BUILD.fullmatch(value):
        raise ValueError("BUILD must be YYYYMMDD")
    try:
        datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("BUILD must be a valid calendar date") from exc
    return value


def read_release_metadata(root: Path = ROOT) -> ReleaseMetadata:
    root = Path(root)
    return ReleaseMetadata(
        validate_version((root / "VERSION").read_text(encoding="utf-8").strip()),
        validate_build((root / "BUILD").read_text(encoding="utf-8").strip()),
    )


def read_runtime_metadata(root: Path = ROOT,
                          environ: Mapping[str, str] | None = None) -> ReleaseMetadata:
    """Use packaged identity; permit old env fallbacks only for absent files.

    Invalid or unreadable present files fail rather than accepting an override.
    Missing metadata files are supported only for legacy/unpackaged development.
    """
    root = Path(root)
    env = os.environ if environ is None else environ
    values = []
    for filename, key, fallback, validator in (
        ("VERSION", "APP_VERSION", "0.0.0", validate_version),
        ("BUILD", "APP_BUILD", "unknown", validate_build),
    ):
        path = root / filename
        try:
            value = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            if path.is_symlink():
                raise ValueError(filename + " must not be a broken symlink")
            value = (env.get(key) or fallback).strip() or fallback
            if filename == "BUILD" and value == "unknown":
                values.append(value)
                continue
        values.append(validator(value))
    return ReleaseMetadata(*values)


def resolve_build(explicit: str | None = None,
                  source_date_epoch: str | int | None = None,
                  now: datetime | None = None) -> str:
    """Freeze one build date; explicit identity wins over clocks/reproducibility.

    Call this once at the workflow/package/build boundary. Downstream steps
    reuse the result; they must not independently resolve a new date at midnight.
    SOURCE_DATE_EPOCH is a nonnegative integral POSIX timestamp when supplied.
    """
    if explicit is not None:
        return validate_build(explicit)
    if source_date_epoch is not None:
        if isinstance(source_date_epoch, bool) or not re.fullmatch(r"[0-9]+", str(source_date_epoch)):
            raise ValueError("SOURCE_DATE_EPOCH must be a nonnegative integer")
        try:
            moment = datetime.fromtimestamp(int(source_date_epoch), timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError("SOURCE_DATE_EPOCH is outside the supported datetime range") from exc
    else:
        moment = datetime.now(timezone.utc) if now is None else now
    if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Build time must be an aware datetime")
    return validate_build(moment.astimezone(ZoneInfo(BUILD_TIMEZONE)).strftime("%Y%m%d"))


def write_build(root: Path, build: str) -> None:
    """Atomically replace BUILD, retaining all unrelated release evidence."""
    root = Path(root)
    validate_build(build)
    validate_version((root / "VERSION").read_text(encoding="utf-8").strip())
    target = root / "BUILD"
    if target.is_symlink():
        raise ValueError("BUILD must not be a symlink")
    temporary = root / ".BUILD.cir-tmp"
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("A temporary BUILD update already exists")
    own_temporary = False
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            own_temporary = True
            stream.write(build + "\n")
        temporary.chmod(0o644)
        temporary.replace(target)
        own_temporary = False
    finally:
        if own_temporary and temporary.exists():
            temporary.unlink()
