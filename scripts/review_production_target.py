#!/usr/bin/env python3
"""Resolve only an immutable recorded image for periodic security review.

This preflight does not approve an image or renew a risk acceptance. Pending
production metadata blocks the review; mutable tags are never substituted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
_COMPONENT = r'[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*'
_REGISTRY = r'[a-z0-9]+(?:[.-][a-z0-9]+)*(?::[0-9]+)?'
_IMAGE = re.compile(rf'(?:{_REGISTRY}/)?{_COMPONENT}(?:/{_COMPONENT})*@sha256:[0-9a-f]{{64}}')


def resolve_target(root: Path = ROOT) -> str:
    value = (Path(root) / 'PRODUCTION_IMAGE_DIGEST').read_text(encoding='utf-8').strip()
    if value.startswith('PENDING_'):
        raise ValueError('PRODUCTION_IMAGE_DIGEST is ' + value + '; no approved immutable image is recorded for review')
    if not _IMAGE.fullmatch(value) or '/' not in value.split('@', 1)[0]:
        raise ValueError('PRODUCTION_IMAGE_DIGEST must be a repository reference pinned by sha256, not a mutable tag')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--github-output', type=Path)
    parser.add_argument('--summary', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        image = resolve_target(args.root)
        report = {'status': 'target-resolved', 'image': image, 'production_approval': False}
        if args.github_output:
            with args.github_output.open('a', encoding='utf-8') as stream:
                stream.write('image=' + image + '\n')
        message = 'Immutable review target: `' + image + '`. Vulnerability gates still need to pass.'
        result = 0
    except (OSError, ValueError) as exc:
        report = {'status': 'blocked', 'error': str(exc), 'production_approval': False}
        message = 'Security review blocked: ' + str(exc)
        print(message, file=sys.stderr)
        result = 1
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if args.summary:
        with args.summary.open('a', encoding='utf-8') as stream:
            stream.write(message + '\n\n')
    if result == 0:
        print(message)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
