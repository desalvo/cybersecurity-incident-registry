#!/usr/bin/env python3
"""Idempotent, least-privilege GitHub Issues notifications for scheduled CIR security checks.

Only called from trusted main/scheduled workflows. Never modifies risk acceptance.
"""
import argparse
import json
import os
import subprocess
import sys


def gh(*args):
    return subprocess.run(['gh', *args], check=True, capture_output=True, text=True).stdout


def notify(title, result, run_url, context, repository):
    if result not in ('success', 'failure', 'cancelled', 'skipped'):
        raise ValueError('Unexpected result')
    if not repository or not run_url.startswith('https://github.com/'):
        raise ValueError('Invalid repository or run URL')
    if not os.environ.get('GH_TOKEN'):
        raise RuntimeError('GH_TOKEN is required')
    existing = json.loads(gh('issue', 'list', '-R', repository, '--state', 'all',
                             '--limit', '200', '--json', 'number,title,state'))
    match = next((x for x in existing if x['title'] == title), None)
    body = (f'Automated CIR security review: **{result.upper()}**\n\n'
            f'Context: {context}\n\nRun: {run_url}\n\n'
            'Review the Trivy/SCA artifacts, fix actionable findings and rerun the checks. '
            'Expired risk acceptance requires explicit review; this automation never renews it.')
    if result == 'success':
        if match and match['state'] == 'OPEN':
            gh('issue', 'comment', str(match['number']), '-R', repository, '--body', body)
            gh('issue', 'close', str(match['number']), '-R', repository,
               '--reason', 'completed')
        return
    if match and match['state'] == 'OPEN':
        gh('issue', 'comment', str(match['number']), '-R', repository, '--body', body)
    elif match:
        gh('issue', 'reopen', str(match['number']), '-R', repository)
        gh('issue', 'comment', str(match['number']), '-R', repository, '--body', body)
    else:
        gh('issue', 'create', '-R', repository, '--title', title, '--body', body)


def main():
    parser = argparse.ArgumentParser()
    for name in ('title', 'result', 'run-url', 'context', 'repository'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    notify(args.title, args.result, args.run_url, args.context, args.repository)


if __name__ == '__main__':
    main()
