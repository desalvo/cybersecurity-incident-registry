"""Disposable visual-coverage test assets only; never publish them as browser evidence."""
from __future__ import annotations
import hashlib
from pathlib import Path


def generated_pdf_preview(directory: Path) -> dict:
    """Write a valid, disposable PDF and PNG for test-manifest integrity checks."""
    from PIL import Image
    from reportlab.pdfgen import canvas
    pdf = directory / 'test-only-mapped-document.pdf'
    png = directory / 'test-only-mapped-document.png'
    c = canvas.Canvas(str(pdf), pagesize=(595, 842))
    c.setFont('Helvetica', 16)
    c.drawString(70, 765, 'CIR / PDF test-only: mapped form with synthetic data')
    c.drawString(70, 717, 'RIFERIMENTO: TEST-2026-0001')
    c.drawString(70, 682, 'STATO: synthetic fixture')
    c.save()
    Image.new('RGB', (845, 1192), (246, 250, 252)).save(png)
    h = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    return {'source_kind': 'cir-generated-mapped-acroform',
            'pdf_file': pdf.name, 'pdf_sha256': h(pdf),
            'png_file': png.name, 'png_sha256': h(png),
            'renderer': 'test-only'}
