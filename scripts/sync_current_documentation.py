#!/usr/bin/env python3
"""Keep only the current (unversioned) CIR training artifacts in the repository.

Called after provenance verification, before both source packaging and the
post-main-merge publication PR. Never removes screenshots, manuals or authored
media/provenance source assets.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import shutil

CURRENT = {'CIR_Operational_Training_IT.pptx',
           'CIR_Operational_Training_Visual.pptx',
           'CIR_Operational_Training_Visual.pdf',
           'CIR_Operational_Training_Visual_EN.pptx', 'CIR_Operational_Training_Visual_EN.pdf'}
LEGACY = re.compile(r'^CIR_Operational_Training_Visual_RC\d+\.(?:pptx|pdf)$')
ALSO_LEGACY = {'CIR_Operational_Training_Extended_IT.pptx', 'CIR_SPAM_Workflow_Module.pptx'}


def sync(root: Path, pptx: Path, pdf: Path, receipt: Path | None = None,
         pptx_en: Path | None = None, pdf_en: Path | None = None, receipt_en: Path | None = None) -> list[str]:
    target = root / 'docs/presentation'
    if not target.is_dir():
        raise ValueError('No presentation directory at ' + str(target))
    for source, ending in ((pptx, '.pptx'), (pdf, '.pdf')):
        if not source.is_file() or source.is_symlink() or source.suffix != ending or source.stat().st_size < 3000:
            raise ValueError('Missing or invalid verified document: ' + str(source))
    if any(v is not None for v in (pptx_en, pdf_en, receipt_en)):
        if not all(v is not None for v in (pptx_en, pdf_en, receipt_en)):
            raise ValueError('English PPTX, PDF and verified receipt must be supplied together')
        for source, ending in ((pptx_en, '.pptx'), (pdf_en, '.pdf'), (receipt_en, '.json')):
            if not source.is_file() or source.is_symlink() or source.suffix != ending or source.stat().st_size < 200:
                raise ValueError('Missing or invalid English training artifact: '+str(source))
    if receipt is not None and (not receipt.is_file() or receipt.is_symlink()):
        raise ValueError('Missing visual provenance receipt')
    removed = []
    for item in target.iterdir():
        if item.is_symlink():
            raise ValueError('Symlink in presentation directory: ' + str(item))
        if item.is_file() and (LEGACY.fullmatch(item.name) or item.name in ALSO_LEGACY):
            removed.append(item.name)
            item.unlink()
        elif item.is_dir() and re.fullmatch(r'CIR_Operational_Training_Visual_RC\d+', item.name):
            removed.append(item.name + '/')
            shutil.rmtree(item)
    for source, dest in ((pptx, 'CIR_Operational_Training_Visual.pptx'),
                         (pdf, 'CIR_Operational_Training_Visual.pdf')):
        destination = target / dest
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
    if receipt is not None:
        shutil.copyfile(receipt, target / 'visual-training-receipt.json')
    if pptx_en is not None:
        for source, dest in ((pptx_en, 'CIR_Operational_Training_Visual_EN.pptx'),
                             (pdf_en, 'CIR_Operational_Training_Visual_EN.pdf'),
                             (receipt_en, 'visual-training-en-receipt.json')):
            destination=target/dest
            if source.resolve()!=destination.resolve():
                shutil.copyfile(source,destination)
    return sorted(removed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--pptx', required=True, type=Path)
    parser.add_argument('--pdf', required=True, type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--pptx-en',type=Path)
    parser.add_argument('--pdf-en',type=Path)
    parser.add_argument('--receipt-en',type=Path)
    args = parser.parse_args()
    print('Synchronized current CIR training; obsolete artifacts:', sync(args.root, args.pptx, args.pdf, args.receipt, args.pptx_en, args.pdf_en, args.receipt_en))


if __name__ == '__main__':
    main()
