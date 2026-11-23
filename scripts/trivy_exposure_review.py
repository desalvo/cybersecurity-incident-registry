#!/usr/bin/env python3
"""Generate an evidence-only multiarchitecture vulnerability review; never approve risk."""
import argparse, csv, json
from pathlib import Path

DOCUMENT = {'libxml2','libexpat1','libraptor2-0','libtiff6','libsqlite3-0','libx11-6','libx11-data','libxrender1'}
NETWORK = {'libssl3t64','openssl','openssl-provider-legacy','libcurl3t64-gnutls','libcurl4t64'}
SYSTEM = {'bsdutils','libblkid1','liblastlog2-2','libmount1','libsmartcols1','libuuid1','login','mount','util-linux','libacl1','libsystemd0','libudev1'}
GNUPG = {'dirmngr','gnupg','gnupg-l10n','gpg','gpg-agent','gpgconf','gpgsm'}

def group(pkg):
    if pkg in DOCUMENT: return 'document_or_data_parser'
    if pkg in NETWORK: return 'network_or_crypto'
    if pkg in SYSTEM: return 'system_or_privileged'
    if pkg in GNUPG: return 'gnupg_transitive'
    return 'other_runtime'

def parse(path):
    data=json.loads(Path(path).read_text())
    if not isinstance(data.get('Results'),list): raise ValueError('Missing Trivy Results')
    rows={}
    for result in data['Results']:
        for v in result.get('Vulnerabilities') or []:
            if v.get('Severity') not in ('HIGH','CRITICAL'): continue
            key=(v['VulnerabilityID'],v['PkgName'],v.get('InstalledVersion',''))
            if key in rows: raise ValueError('Duplicate vulnerability entry: '+str(key))
            rows[key]={'cve':key[0],'package':key[1],'installed':key[2], 'severity':v['Severity'], 'fixed_version':v.get('FixedVersion') or '', 'status':v.get('Status') or ''}
    return rows

def build(amd,arm):
    left,right=parse(amd),parse(arm)
    allkeys=sorted(set(left)|set(right))
    result=[]
    for key in allkeys:
        a,b=left.get(key),right.get(key)
        v=a or b
        if a and b and (a['severity'],a['fixed_version']) != (b['severity'],b['fixed_version']):
            raise ValueError('Conflicting architecture findings: '+str(key))
        pkg=v['package']; cat=group(pkg)
        result.append({**v,'category':cat,'amd64':'yes' if a else 'no','arm64':'yes' if b else 'no',
            'decision':'REMEDIATE_OR_REVIEW',
            'exposure':'unverified', 'fix_available':'check_vendor_advisory',
            'review_owner':'unassigned','reviewed_on':'','expires_on':'',
            'review_note':('Untrusted document input possible; prioritize patching' if cat=='document_or_data_parser' else 'Confirm actual invocation and container controls')})
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--amd64',required=True);p.add_argument('--arm64',required=True);p.add_argument('--csv',required=True);p.add_argument('--json',required=True)
    args=p.parse_args(); rows=build(args.amd64,args.arm64)
    Path(args.csv).parent.mkdir(parents=True,exist_ok=True)
    with open(args.csv,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['cve']);w.writeheader();w.writerows(rows)
    summary={'amd64_occurrences':sum(x['amd64']=='yes' for x in rows),'arm64_occurrences':sum(x['arm64']=='yes' for x in rows),
      'distinct_cves':len({x['cve'] for x in rows}), 'critical':sorted({x['cve'] for x in rows if x['severity']=='CRITICAL'}),
      'categories':{c:sum(x['category']==c for x in rows) for c in sorted({x['category'] for x in rows})},
      'decision':'NOT_APPROVED', 'production_gate':'MUST_REMAIN_BLOCKING',
      'limitations':['No runtime reachability testing','No Debian vendor fix verification','No approved risk acceptance']}
    Path(args.json).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
