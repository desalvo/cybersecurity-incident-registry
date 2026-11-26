#!/usr/bin/env python3
"""Avoid re-publishing docs on the merge of the bot's own generated docs PR.

Authored specs, app code and workflows still trigger documentation publication,
even when a Docker image rebuild is not needed.
"""
from __future__ import annotations
import argparse
from pathlib import PurePosixPath
import subprocess


def generated(path: str) -> bool:
    if path in {'PRODUCTION_IMAGE_DIGEST', 'k8s/kustomization.yaml',
                'docs/UI_SCREENSHOTS_SOURCE.json', 'docs/UI_SCREENSHOTS_BUILD.json'}:
        return True
    if path.startswith('app/static/help/ui-runtime/'):
        return path.endswith(('.png', '.jpg', '.json'))
    if path.startswith('docs/') and '/' not in path[5:] and path.endswith('.pdf'):
        return True
    if path.startswith('docs/presentation/'):
        name = PurePosixPath(path).name
        return (name.endswith(('.pptx', '.pdf')) or
                name.startswith('manual-first-page-') and name.endswith('.png') or
                name in {'presentation-receipt.json', 'visual-training-receipt.json'})
    return False


def needs_publication(changed: list[str]) -> bool:
    return not changed or any(not generated(item) for item in changed)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--before', required=True)
    p.add_argument('--head', required=True)
    p.add_argument('--publication-output', required=True)
    args = p.parse_args()
    if args.before.strip('0'):
        changed = subprocess.check_output(['git', 'diff', '--name-only', args.before, args.head], text=True).splitlines()
    else:
        changed = []
    publication = needs_publication(changed)
    with open(args.publication_output, 'a', encoding='utf8') as output:
        output.write('documentation_needed='+str(publication).lower()+'\n')
    print('Documentation publication needed:', publication, 'changed:', len(changed))

if __name__ == '__main__':
    main()
