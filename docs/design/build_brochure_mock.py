#!/usr/bin/env python3
"""Build a photographic CIR brochure proposal for explicit visual approval.

All copy remains searchable PDF text. Photographs are illustrative generated
assets, with provenance maintained under docs/visual-assets/. No stock download,
network access or application runtime is required. Output must be selected
explicitly; this prototype never overwrites the adopted documentation.
"""
import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'docs/visual-assets'
VERSION = (ROOT / 'VERSION').read_text().strip()
NAVY = '#071D2B'
TEAL = '#087C75'
MINT = '#63DDCC'
AMBER = '#E6B37A'
INK = '#102C3B'
MUTED = '#4D6570'
PAPER = '#F7F6F1'
FONT, BOLD = 'Helvetica', 'Helvetica-Bold'
regular = Path('/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf')
if regular.is_file() and regular.with_name('NotoSans-Bold.ttf').is_file():
    pdfmetrics.registerFont(TTFont('CIRBrochureNoto', str(regular)))
    pdfmetrics.registerFont(TTFont('CIRBrochureNotoBold', str(regular.with_name('NotoSans-Bold.ttf'))))
    pdfmetrics.registerFontFamily('CIRBrochureNoto', normal='CIRBrochureNoto', bold='CIRBrochureNotoBold')
    FONT, BOLD = 'CIRBrochureNoto', 'CIRBrochureNotoBold'
W, H = A4


def paragraph(c, text, x, top, width, size=11, color=INK, bold=False, leading=1.38):
    p = Paragraph(text, ParagraphStyle('cir', fontName=BOLD if bold else FONT,
        fontSize=size, leading=size * leading, textColor=colors.HexColor(color), spaceAfter=0))
    _, height = p.wrap(width, H)
    if top + height > H - 16:
        raise ValueError(f'Brochure text overflows: {text[:70]}')
    p.drawOn(c, x, H - top - height)
    return top + height


def rect(c, x, top, width, height, color, alpha=1):
    c.saveState()
    c.setFillColor(colors.HexColor(color))
    c.setFillAlpha(alpha)
    c.rect(x, H - top - height, width, height, fill=1, stroke=0)
    c.restoreState()


def photo(c, name, x, top, width, height, focus_x=.5, focus_y=.5):
    """Place the original photo in a PDF clipping rectangle without alteration."""
    path = ASSETS / name
    if not path.is_file():
        raise FileNotFoundError(f'Required original project asset: {path}')
    image = ImageReader(str(path))
    iw, ih = image.getSize()
    scale = max(width / iw, height / ih)
    dw, dh = iw * scale, ih * scale
    c.saveState()
    clip = c.beginPath()
    clip.rect(x, H - top - height, width, height)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(image, x - (dw - width) * focus_x,
        H - top - height - (dh - height) * (1 - focus_y),
        width=dw, height=dh, mask='auto')
    c.restoreState()


def brand(c, section, white=False):
    color = '#FFFFFF' if white else INK
    paragraph(c, 'CIR', 40, 24, 80, 18, color, True)
    paragraph(c, section, 104, 31, W - 144, 8.3, '#DBECEC' if white else MUTED, True)


def footer(c, page, en=False, white=False):
    color = '#BED2D9' if white else MUTED
    paragraph(c, 'Graphic proposal · pending approval' if en else 'Proposta grafica · da approvare', 40, H - 51, W - 100, 7.7, MINT if white else TEAL, True)
    paragraph(c, f'Cybersecurity Incident Registry / {VERSION}', 40, H - 34, W - 100, 7.6, color)
    c.setFillColor(colors.HexColor(color))
    c.setFont(FONT, 7.6)
    c.drawRightString(W - 40, 24, f'{page:02}')


def build(en=False, *, output):
    out = Path(output).resolve()
    if out in {ROOT / 'docs' / name for name in ('brochure_cybersecurity_incident_registry.pdf', 'brochure_cybersecurity_incident_registry_en.pdf')}:
        raise ValueError('The visual proposal must not replace the adopted brochure.')
    out.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out), pagesize=A4, pageCompression=1, invariant=1)
    c.setTitle('Cybersecurity Incident Registry - Brochure design proposal' if en else 'Cybersecurity Incident Registry - Proposta grafica brochure')
    c.setAuthor('Alessandro De Salvo')
    c.setSubject('Photographic product brochure; original illustrative generated imagery')

    # 01: A photographic first impression with a strong, native-text identity.
    rect(c, 0, 0, W, H, NAVY)
    photo(c, 'operations-editorial.png', 0, 0, W, 492, focus_x=.54)
    rect(c, 0, 0, W, 85, NAVY, .62)
    brand(c, 'CYBERSECURITY INCIDENT REGISTRY', white=True)
    rect(c, 40, 473, 46, 4, MINT)
    paragraph(c, 'Every incident.<br/>A clear response.' if en else 'Ogni incidente.<br/>Una risposta chiara.', 40, 518, W - 80, 36, '#FFFFFF', True, 1.15)
    paragraph(c, 'Coordinate people, procedures and evidence<br/>in one configurable operational registry.' if en else 'Coordina persone, procedure ed evidenze<br/>in un registro operativo configurabile.', 42, 626, W - 84, 14.5, '#D9E8ED', leading=1.42)
    paragraph(c, 'SHARED CONFIGURATION. LOCAL RESPONSIBILITY.' if en else 'CONFIGURAZIONE CONDIVISA. RESPONSABILITÀ LOCALI.', 42, 701, W - 84, 9, MINT, True)
    paragraph(c, 'Original illustrative photographs generated for CIR.' if en else 'Fotografie illustrative originali generate per CIR.', 42, 765, W - 84, 7.5, '#BED2D9')
    footer(c, 1, en, white=True)
    c.showPage()

    # 02: A vertical editorial photograph accompanies the operational sequence.
    rect(c, 0, 0, W, H, PAPER)
    brand(c, 'THE OPERATIONAL PATH' if en else 'IL PERCORSO OPERATIVO')
    paragraph(c, 'From the first report<br/>to a documented outcome.' if en else 'Dalla prima segnalazione<br/>all’esito documentato.', 40, 82, W - 80, 28, INK, True, 1.18)
    photo(c, 'infrastructure-editorial.png', 0, 209, 230, 577, focus_x=.40)
    rect(c, 0, 611, 230, 175, NAVY, .86)
    paragraph(c, 'Keep the context.<br/>Make the next<br/>action visible.' if en else 'Conserva il contesto.<br/>Rendi visibile<br/>il prossimo passo.', 29, 638, 176, 20, '#FFFFFF', True, 1.22)
    blocks_en = [
        ('Record and classify', 'Create the incident in the correct tenant. Identify severity, type, involved people and the first evidence.'),
        ('Follow the workflow', 'Configurable steps, conditions, required actions and procedural warnings keep the expected work visible.'),
        ('Collect and notify', 'Attach documents, generate forms and prepare notifications. Keep actions, evidence and reports linked to the incident.'),
        ('Verify and close', 'Review outstanding requirements, record the outcome and retain a coherent history of the response.'),
    ]
    blocks_it = [
        ('Registra e classifica', 'Apri l’incidente nel tenant corretto. Identifica gravità, tipologia, persone coinvolte e prime evidenze.'),
        ('Segui il workflow', 'Step configurabili, condizioni, azioni richieste e avvisi procedurali rendono visibile il lavoro previsto.'),
        ('Documenta e notifica', 'Allega documenti, genera moduli e prepara notifiche. Conserva azioni, evidenze e report nel contesto dell’incidente.'),
        ('Verifica e chiudi', 'Controlla i requisiti ancora aperti, registra l’esito e conserva una cronologia coerente della risposta.'),
    ]
    for i, (head, body) in enumerate(blocks_en if en else blocks_it):
        y = 227 + i * 137
        paragraph(c, f'0{i+1}', 263, y, 42, 16, TEAL, True)
        paragraph(c, head, 309, y + 1, W - 349, 12.6, INK, True)
        paragraph(c, body, 265, y + 36, W - 306, 10.9, MUTED)
        if i < 3:
            c.setStrokeColor(colors.HexColor('#D5DFDF'))
            c.setLineWidth(.7)
            c.line(265, H - y - 119, W - 40, H - y - 119)
    footer(c, 2, en)
    c.showPage()

    # 03: Shared configuration and local editable variants, with explicit limits.
    rect(c, 0, 0, W, H, PAPER)
    photo(c, 'infrastructure-editorial.png', 0, 0, W, 281, focus_y=.45)
    rect(c, 0, 0, W, 281, NAVY, .55)
    brand(c, 'TENANTS DEFAULT', white=True)
    paragraph(c, 'A shared catalogue.<br/>Room for local variations.' if en else 'Un catalogo condiviso.<br/>Spazio alle varianti locali.', 40, 137, W - 80, 28, '#FFFFFF', True, 1.18)
    boxes_en = [
        ('One configuration source', 'Tenants Default is separate from operational default. If absent, it is initialized from default configuration. Existing configuration is preserved.'),
        ('Correct local references', 'Labels and parameters retain durable provenance. ID collisions create new local records and workflow imports resolve the exact destination references.'),
        ('Repeatable, editable imports', 'Import the same workflow under different names. Edit local structures and explicitly customize parameter dependencies to create independent variants.'),
        ('Controlled obsolescence', 'Marking the source obsolete blocks new imports and retires all installed copies, including customized ones. Administrators receive in-application notices.'),
    ]
    boxes_it = [
        ('Un punto di configurazione', 'Tenants Default è distinto dal default operativo. Se assente nasce dalla sua configurazione. Una sorgente già presente viene conservata.'),
        ('Riferimenti locali corretti', 'Label e parametri mantengono la provenienza. Le collisioni di ID creano nuovi record locali e i workflow importati usano i riferimenti esatti.'),
        ('Import ripetibili e modificabili', 'Importa lo stesso workflow con nomi diversi. Modifica le strutture locali e personalizza le dipendenze per creare varianti indipendenti.'),
        ('Obsolescenza controllata', 'Rendere obsoleta la sorgente blocca nuovi import e ritira tutte le copie, anche personalizzate. Gli amministratori ricevono avvisi nell’applicazione.'),
    ]
    for i, (head, body) in enumerate(boxes_en if en else boxes_it):
        x = 40 if i % 2 == 0 else 313
        y = 321 if i < 2 else 497
        width = 242
        rect(c, x, y, 26, 3, TEAL)
        end = paragraph(c, head, x, y + 18, width, 13.1, INK, True, 1.25)
        paragraph(c, body, x, end + 12, width, 10.8, MUTED, leading=1.46)
    rect(c, 40, 683, W - 80, 105, NAVY)
    paragraph(c, 'Protect the history. Transfer the setup.' if en else 'Proteggi lo storico. Trasferisci il setup.', 57, 700, W - 114, 13, '#FFFFFF', True)
    paragraph(c, 'Records used by incidents cannot be deleted. Export all Tenants Default to a new instance. Full Export and anonymized bootstrap include the special tenant; existing incidents retain their history.' if en else 'I record usati da incidenti non sono cancellabili. Esporta tutto Tenants Default in una nuova istanza. Full Export e bootstrap anonimizzato includono il tenant speciale; gli incidenti esistenti conservano lo storico.', 57, 731, W - 114, 9.4, '#D9E8ED', leading=1.38)
    footer(c, 3, en)
    c.showPage()

    # 04: Deployment, integrations and an honest route from candidate to operation.
    rect(c, 0, 0, W, H, PAPER)
    photo(c, 'operations-editorial.png', 0, 0, W, 219, focus_y=.50)
    rect(c, 0, 0, W, 219, NAVY, .66)
    brand(c, 'YOUR OPERATING ENVIRONMENT' if en else 'IL TUO AMBIENTE OPERATIVO', white=True)
    paragraph(c, 'Procedures. Documents.<br/>Everything in context.' if en else 'Procedure. Documenti.<br/>Tutto nel contesto.', 40, 94, W - 80, 27, '#FFFFFF', True, 1.18)
    sections_en = [
        ('Interoperability and configuration', 'SSO, audit and automatic notifications. Custom workflow import and fillable PDFs. Documents in CIR, CIR + Alfresco or Alfresco only; delete, read-only sync and incident reports follow tenant settings.'),
        ('A choice of deployment paths', 'Docker Hub, Docker Compose, Kubernetes and OpenShift. Helm chart and console Template, PostgreSQL, existing Secrets and persistent storage. Restricted containers. Publish and configure a Helm repository for the graphical catalogue.'),
        ('Accessible workspaces', 'Responsive desktop and mobile interface, accessibility features and Italian/English localization, with reference to AGID guidelines. Optional AlBot knowledge base. No accessibility certification is implied.'),
        ('A practical learning session', 'The PowerPoint and training guide follow a fictitious phishing case from opening through containment, notification and closure. A second exercise compares local workflow variants and source obsolescence.'),
    ]
    sections_it = [
        ('Interfacciabilità e Configurabilità completa', 'SSO, audit e Notifiche automatiche. Import di workflow custom e PDF compilabili. Documenti in CIR, CIR + Alfresco o Solo Alfresco; delete, sync read-only e report incidente seguono le impostazioni del tenant.'),
        ('Più percorsi di installazione', 'Docker Hub, Docker Compose, Kubernetes e OpenShift. Chart Helm e Template della console, PostgreSQL, Secret esistenti e storage persistente. Container con privilegi limitati. Pubblica e configura il repository Helm per il catalogo grafico.'),
        ('Spazi di lavoro accessibili', 'Interfaccia responsive desktop e mobile, funzioni di accessibilità e localizzazione in italiano e inglese, con riferimento alle linee guida AGID. Knowledge base opzionale per AlBot. Nessuna certificazione di accessibilità implicita.'),
        ('Una sessione didattica concreta', 'PowerPoint e guida seguono un caso fittizio di phishing, dall’apertura al contenimento, alla notifica e alla chiusura. Un secondo esercizio confronta varianti locali dei workflow e obsolescenza dalla sorgente.'),
    ]
    for i, (head, body) in enumerate(sections_en if en else sections_it):
        x = 40 if i % 2 == 0 else 313
        y = 252 if i < 2 else 424
        width = 242
        end = paragraph(c, head, x, y, width, 12.6, TEAL, True, 1.22)
        paragraph(c, body, x, end + 10, width, 9.7, INK, leading=1.40)
    c.setStrokeColor(colors.HexColor('#CDDADA'))
    c.line(40, H - 588, W - 40, H - 588)
    paragraph(c, 'Release with evidence' if en else 'Rilascio con evidenze', 40, 603, W - 80, 11.5, TEAL, True)
    paragraph(c, 'Production promotion requires tests, real PostgreSQL, SCA and Trivy scans on amd64/arm64. This source candidate does not approve a new production image. Consult HANDOFF and verification results; the previous risk acceptance expired on 20 October 2026.' if en else 'La promozione production richiede test, PostgreSQL reale, SCA e Trivy su amd64/arm64. Il candidato sorgente non approva una nuova immagine production. Consultare Handoff e verifiche: la precedente risk acceptance è scaduta il 20 ottobre 2026.', 40, 628, W - 80, 9, MUTED, leading=1.37)
    rect(c, 0, 699, W, H - 699, NAVY)
    paragraph(c, 'Open source. Operational documentation.' if en else 'Open source. Documentazione operativa.', 40, 719, W - 80, 12, '#FFFFFF', True)
    paragraph(c, 'European Union Public Licence (EUPL-1.2)<br/>Alessandro De Salvo - Alessandro.DeSalvo@roma1.infn.it<br/><link href="https://github.com/desalvo/cybersecurity-incident-registry" color="#63DDCC">https://github.com/desalvo/cybersecurity-incident-registry</link>', 40, 749, W - 80, 8.4, '#D9E8ED', leading=1.48)
    footer(c, 4, en, white=True)
    c.save()
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='Proposal PDF path, separate from adopted docs.')
    parser.add_argument('--language', choices=('it', 'en'), default='it')
    args = parser.parse_args()
    print(build(args.language == 'en', output=args.output))
