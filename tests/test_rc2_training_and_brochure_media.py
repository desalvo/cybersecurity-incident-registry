"""0.10.0-1 RC2: media provenance and pedagogical release regressions."""
from pathlib import Path
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]

def test_brochure_media_are_local_and_reused_on_all_pages():
    from scripts.audit_documentation_media import check
    result=check(ROOT,ROOT/'docs')
    assert result['pages']==8 and result['brochures']==2
    assert all(entry['approved_only'] and entry['embedded_images']==11 for entry in result['files'].values())

def test_training_embedded_media_are_allowlisted():
    from scripts.audit_training_media import audit
    assert audit(ROOT/'docs/presentation/CIR_Operational_Training_IT.pptx',ROOT)>=8

def test_incident_pdf_has_six_distinct_educational_steps_without_fake_screenshots():
    pdf=PdfReader(ROOT/'docs/CIR_Incident_Laboratory_IT.pdf')
    assert len(pdf.pages)==7
    for index,title in enumerate(('Apertura e classificazione','Presa in carico',
                                  'Contenimento ed evidenze','Analisi e documentazione',
                                  'Notifica e verifica','Chiusura e riesame'),start=1):
        text=pdf.pages[index].extract_text()
        assert title in text
        assert 'ACQUISIZIONE CI IN ATTESA' in text
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
