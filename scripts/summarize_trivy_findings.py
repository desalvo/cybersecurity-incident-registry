#!/usr/bin/env python3
"""Produce a non-approving inventory of Trivy findings for security review."""
import argparse
import collections
import json
from pathlib import Path


def summarize(report):
    output = []
    for result in report.get('Results', []):
        for item in result.get('Vulnerabilities') or []:
            if item.get('Severity') not in ('HIGH', 'CRITICAL'):
                continue
            output.append({
                'target': result.get('Target'),
                'vulnerability': item.get('VulnerabilityID'),
                'severity': item.get('Severity'),
                'package': item.get('PkgName'),
                'installed_version': item.get('InstalledVersion'),
                'fixed_version': item.get('FixedVersion') or None,
                'status': item.get('Status') or None,
            })
    return sorted(output, key=lambda x: (x['severity'] != 'CRITICAL', x['package'] or '', x['vulnerability'] or ''))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results = {}
    for path in args.reports:
        findings = summarize(json.loads(path.read_text()))
        results[path.name] = {'findings': findings, 'count': len(findings),
                              'severity': dict(collections.Counter(x['severity'] for x in findings)),
                              'fix_available': sum(bool(x['fixed_version']) for x in findings)}
    payload = {'decision': 'REVIEW_REQUIRED_NOT_AN_ACCEPTANCE', 'reports': results}
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
