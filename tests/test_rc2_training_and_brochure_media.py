"""0.10.0-1 RC2: media provenance and pedagogical release regressions."""
from pathlib import Path
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]

def test_brochure_media_are_local_and_reused_on_all_pages():
    from scripts.audit_documentation_media import check
    result=check(ROOT,ROOT/'docs')
    assert result['pages']==8 and result['brochures']==2
    assert all(entry['approved_only'] and entry['embedded_images']==11 for entry in result['files'].values())

def _verify_embedded_presentation_media():
    """Verify the checked-out deck without trusting mutable PDF build receipts.

    The full cross-document attestation is validated in the separate real UI
    documentation CI job and in distribution packaging. The application test
    job regenerates brochures with a fresh BUILD, which deliberately makes a
    previously published receipt stale. Do not suppress such a mismatch in
    production; validate the independent deck/image evidence here instead.
    """
    import hashlib
    import json
    from zipfile import ZipFile
    from scripts.audit_training_media import approved_hashes

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    deck_path = ROOT / 'docs/presentation/CIR_Operational_Training_IT.pptx'
    receipt = json.loads((ROOT / 'docs/presentation/presentation-receipt.json').read_text())
    assert receipt['file'] == deck_path.name
    assert digest(deck_path.read_bytes()) == receipt['sha256']
    approved = approved_hashes(ROOT)
    with ZipFile(deck_path) as deck:
        media = {name: digest(deck.read(name)) for name in deck.namelist()
                 if name.startswith('ppt/media/') and not name.endswith('/')}
        assert len(media) >= 8
        preview_names = set()
        for row in receipt['manual_first_pages']:
            name = row['media_file']
            assert name in media and name not in preview_names
            assert media[name] == row['png_sha256']
            preview_names.add(name)
        screenshot_names = set()
        if receipt['real_screenshots']:
            # Every screenshot embedded in the CI deck is bound to its own
            # immutable receipt, even when PDFs have since been regenerated.
            assert len(receipt['screenshots']) >= 1
            for row in receipt['screenshots']:
                name = row['media_file']
                assert name in media and name not in screenshot_names
                assert media[name] == row['sha256']
                screenshot_names.add(name)
        else:
            assert receipt['screenshots'] == []
        for name, value in media.items():
            assert name in preview_names or name in screenshot_names or value in approved, name
    return receipt


def test_training_embedded_media_are_allowlisted():
    _verify_embedded_presentation_media()


def test_incident_pdf_has_six_distinct_educational_steps_without_fake_screenshots():
    pdf = PdfReader(ROOT/'docs/CIR_Incident_Laboratory_IT.pdf')
    assert len(pdf.pages) == 7
    receipt = _verify_embedded_presentation_media()
    for index,title in enumerate(('Apertura e classificazione','Presa in carico',
                                  'Contenimento ed evidenze','Analisi e documentazione',
                                  'Notifica e verifica','Chiusura e riesame'),start=1):
        text = pdf.pages[index].extract_text()
        assert title in text
        if receipt['real_screenshots']:
            assert 'ACQUISIZIONE CI IN ATTESA' not in text
        else:
            assert 'ACQUISIZIONE CI IN ATTESA' in text or 'Build ' in text
    assert '0.10.0-1' in pdf.pages[0].extract_text()


def test_admin_manuals_contain_independent_architecture_paths():
    for name,heading in [('documentazione_amministrativa.pdf','Installazione e bootstrap per architettura'),
                         ('administrator_documentation_en.pdf','Installation and bootstrap by architecture')]:
        pdf=PdfReader(ROOT/'docs'/name)
        text='\n'.join(page.extract_text() for page in pdf.pages)
        assert heading in text
        for platform in ('Docker','Podman','Kubernetes','OpenShift'):
            assert platform in text

def test_ci_uses_real_incident_and_checks_arrows_and_brochure_artwork():
    workflow=(ROOT/'.github/workflows/ci-release.yml').read_text()
    capture=(ROOT/'scripts/capture_ui_screenshots.py').read_text()
    assert 'Audit brochure artwork provenance and all editorial pages' in workflow
    assert 'scripts/audit_documentation_media.py' in workflow
    assert '"#incident-workflow .workflow-step-arrow"' in capture
    assert '"incident-desktop"' in capture
