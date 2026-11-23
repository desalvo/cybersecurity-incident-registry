#!/usr/bin/env python3
"""Render the isolated incident-detail mock as native design boards.

These are ReportLab drawings, not browser screenshots.  Data comes from the
adjacent fixtures.json.  The approved home renderer supplies the palette,
logo, vector icons and photographic treatment without modifying its files.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

import fitz
from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HOME = HERE.parent / 'home-v1' / 'render_home.py'
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('approved_home_board', HOME)
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)
PHOTO = home.PHOTO
LOGO = home.LOGO
DRAWING_LOG = []


def lines(text, width, size=12, bold=False):
    font = 'UIB' if bold else 'UI'
    result = []
    for paragraph in str(text).split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = (line + ' ' + word).strip()
            if line and pdfmetrics.stringWidth(candidate, font, size) > width:
                result.append(line)
                line = word
            else:
                line = candidate
        result.append(line)
    return result


class Board(home.Board):
    def __init__(self, c, w, h, label):
        self.c, self.w, self.h = c, w, h
        self.label = label
        c.setPageSize((w, h))
        self.rect(0, 0, w, h, 'paper')
        self.rect(0, 0, w, 34, '#eaf0f4')
        self.text('Mockup incidente · da approvare', 16 if w < 500 else 26, 22,
                  9 if w < 500 else 11, 'muted')
        self.text(label, w - (16 if w < 500 else 26), 22,
                  8.5 if w < 500 else 10, 'muted', anchor='right')

    def text(self, s, x, y, size=12, fill='ink', bold=False, anchor='left'):
        s = str(s)
        width = pdfmetrics.stringWidth(s, 'UIB' if bold else 'UI', size)
        left = x - (width / 2 if anchor == 'center' else width if anchor == 'right' else 0)
        if left < -.5 or left + width > self.w + .5 or y > self.h - 1:
            raise ValueError(f'Out-of-page text on {self.label}: {s!r} at {left}, {y}, width {width}')
        DRAWING_LOG.append({'page': self.label, 'text': s, 'x': round(left, 2),
                            'y': round(y, 2), 'width': round(width, 2), 'size': size})
        super().text(s, x, y, size, fill, bold, anchor)

    def para(self, s, x, y, width, size=12, fill='ink', bold=False, leading=None):
        leading = leading or size * 1.45
        text_lines = lines(s, width, size, bold)
        for index, text in enumerate(text_lines):
            self.text(text, x, y + index * leading, size, fill, bold)
        return y + len(text_lines) * leading

    def pill(self, text, x, y, fill='#edf3fa', fg='blue', size=10, width=None):
        width = width or pdfmetrics.stringWidth(text, 'UIB', size) + 20
        self.rect(x, y, width, 25, fill, 5)
        self.text(text, x + width / 2, y + 17, size, fg, True, 'center')
        return width

    def arrow(self, x, y, vertical=False):
        if vertical:
            self.line(x, y - 9, x, y + 8, '#718fa7', 1.8)
            self.line(x - 4, y + 3, x, y + 8, '#718fa7', 1.8)
            self.line(x + 4, y + 3, x, y + 8, '#718fa7', 1.8)
        else:
            self.line(x - 8, y, x + 8, y, '#718fa7', 1.8)
            self.line(x + 3, y - 4, x + 8, y, '#718fa7', 1.8)
            self.line(x + 3, y + 4, x + 8, y, '#718fa7', 1.8)

    def chevron(self, x, y, down=True, color='#617181'):
        self.line(x - 4, y - (2 if down else -2), x, y + (2 if down else -2), color, 1.4)
        self.line(x, y + (2 if down else -2), x + 4, y - (2 if down else -2), color, 1.4)

    def check(self, x, y, checked=False, size=14):
        self.checkbox(x, y, size)
        if checked:
            self.line(x + 3, y + 7, x + 6, y + 10, 'blue', 1.6)
            self.line(x + 6, y + 10, x + 11, y + 4, 'blue', 1.6)


def topbar(b, data, mobile=False):
    if mobile:
        b.rect(0, 34, 430, 74, 'white')
        b.line(0, 108, 430, 108)
        for yy in [64, 70, 76]:
            b.line(19, yy, 35, yy, 'ink', 1.5)
        b.text('Menu', 47, 77, 13)
        b.text('Tenant attivo', 266, 61, 8, 'muted')
        b.text(data['incident']['tenant'], 266, 81, 12)
        b.chevron(347, 76)
        b.rect(380, 55, 31, 31, '#ebf1f8', 15.5, '#c6d7e9')
        b.text('AO', 395.5, 75.5, 10, 'blue', True, 'center')
        return
    home.sidebar(b)
    b.rect(246, 34, 1290, 84, 'white')
    b.line(246, 118, 1536, 118)
    b.text('Incidenti', 278, 81, 12, 'muted')
    b.text('/', 343, 81, 12, '#afbdc8')
    b.text(data['incident']['reference'], 367, 81, 12, 'ink', True)
    b.text('Tenant attivo', 1022, 81, 11, 'muted')
    b.rect(1108, 57, 137, 39, 'white', 6, '#cad6e0')
    b.text(data['incident']['tenant'], 1121, 81, 12)
    b.chevron(1227, 77)
    b.rect(1271, 59, 34, 34, '#ebf1f8', 17, '#c6d7e9')
    b.text('AO', 1288, 81, 11, 'blue', True, 'center')
    b.text('Admin operativo', 1315, 73, 12)
    b.text(data['user']['role_label'], 1315, 90, 9.5, 'muted')
    b.chevron(1496, 77)


def incident_header(b, data, y=143, mobile=False, compact=False):
    incident = data['incident']
    x, w = (16, 398) if mobile else (278, 1226)
    h = 160 if mobile else 100 if compact else 112
    b.photo(x, y, w, h, 10, mobile)
    b.text('INCIDENTE  /  ' + incident['reference'], x + 20, y + 26,
           8.5 if mobile else 9, '#a0ccd6')
    title = incident.get('name', incident.get('title'))
    if mobile:
        end = b.para(title, x + 20, y + 56, 351, 21, 'white', True, 27)
        b.text('Tenant: ' + incident['tenant'], x + 20, y + h - 18, 10, '#d3e8ee')
    else:
        b.text(title, x + 24, y + 61, 25 if not compact else 23, 'white', True)
        b.text('Tenant: ' + incident['tenant'] + '  ·  Dati dimostrativi', x + 24,
               y + h - 18, 11, '#d3e8ee')
    return y + h


def section_header(b, title, x, y, w, right='', open=True, icon=None):
    b.text(title, x + 20, y + 31, 18 if w > 500 else 17, 'ink', True)
    if right:
        b.text(right, x + w - 45, y + 31, 10.5, 'muted', anchor='right')
    b.chevron(x + w - 24, y + 25, down=not open)


def collapsed(b, title, x, y, w, suffix='', h=52):
    b.rect(x, y, w, h, 'white', 8, 'line')
    b.text(title, x + 18, y + 32, 13 if w > 500 else 12, 'ink', True)
    if suffix:
        b.text(suffix, x + w - 45, y + 31, 10, 'muted', anchor='right')
    b.chevron(x + w - 23, y + h / 2)


def section_nav(b, data, y, mobile=False, compact=False):
    x, w = (16, 398) if mobile else (278, 1226)
    h = 158 if mobile else 40 if compact else 50
    b.rect(x, y, w, h, 'white', 9, 'line')
    offset = 8
    for index, section in enumerate(data['sections']):
        label = section['short']
        if section.get('count'):
            label += '  ' + str(section['count'])
        if mobile:
            sx = x + 7 + (index % 3) * 129
            sy = y + 7 + (index // 3) * 36
            sw = 126
            font = 9.3
        else:
            font = 10.6
            sw = pdfmetrics.stringWidth(label, 'UI', font) + 24
            sx, sy = x + offset, y + (3 if compact else 8)
            offset += sw + 5
        if index == 0:
            b.rect(sx, sy, sw, 34, '#eaf1fa', 5)
        b.text(label, sx + sw / 2, sy + 22, font,
               'blue' if index == 0 else '#476076', index == 0, 'center')
    return y + h


def step_card(b, step, x, y, w, h=324, mobile=False):
    status = step['status']
    upper = {'completed': '#edf7f1', 'current': '#edf4ff', 'pending': '#f2f5f8'}[status]
    accent = {'completed': '#2d7759', 'current': '#2559a6', 'pending': '#667d90'}[status]
    border = '#729bd2' if status == 'current' else '#d5e0e8'
    upper_h = 144
    b.rect(x, y, w, h, 'white', 8, border)
    b.rect(x + 1, y + 1, w - 2, upper_h, upper, 7)
    b.rect(x + 1, y + upper_h - 7, w - 2, 7, upper)
    b.line(x + 1, y + upper_h, x + w - 1, y + upper_h, border)
    b.rect(x + 14, y + 14, 26, 26, accent, 13)
    b.text(str(step['number']).zfill(2), x + 27, y + 32, 10, 'white', True, 'center')
    b.text(step['status_label'], x + 50, y + 32, 9.4 if not mobile else 10.5, accent, True)
    yy = b.para(step['flow_title'], x + 14, y + 61, w - 28,
                12.3 if not mobile else 13.4, 'ink', True, 18)
    flow_end = b.para(step['flow_description'], x + 14, yy + 6, w - 28,
                      11.5 if not mobile else 12, 'muted', leading=16)
    if flow_end > y + upper_h + 1:
        raise ValueError(f'Flow text overflow in step {step["number"]}')
    kind = step['task_description']
    b.text(kind.upper(), x + 14, y + upper_h + 24, 8.5, 'muted', True)
    yy = b.para(step['task_name'], x + 14, y + upper_h + 47, w - 28,
                13.2 if not mobile else 14, 'ink', True, 18)
    note = step.get('detail')
    if note:
        if isinstance(note, dict):
            note = note.get('label') or note.get('text') or ''
        yy = b.para(note, x + 14, yy + 7, w - 28, 10.5, 'muted', leading=15)
    if step.get('deadline'):
        due = step['deadline']
        yy = b.para('Scadenza configurata ' + due['due_short'] + '\nRestano ' + due['remaining'],
                    x + 14, yy + 7, w - 28, 10.2, '#8b5c13', leading=14)
    action = step['action']
    button_y = y + h - 46
    if yy > button_y - 5:
        raise ValueError(f'Task text touches button in step {step["number"]}: {yy} vs {button_y}')
    b.button(action['label'], x + 14, button_y, w - 28, 33,
             primary=(status == 'current'), size=11.3)
    return h


def workflow(b, data, y, mobile=False):
    wf = data['workflow']
    steps = wf['steps']
    x, w = (16, 398) if mobile else (278, 1226)
    if mobile:
        card_h, gap = 334, 29
        h = 99 + len(steps) * card_h + (len(steps) - 1) * gap + 18
        b.rect(x, y, w, h, 'white', 10, 'line')
        section_header(b, 'Fasi procedurali', x, y, w, '1 / 4')
        b.para(wf.get('name', 'Gestione data breach'), x + 18, y + 60, w - 38, 11, 'muted')
        b.text('Sequenza ordinata · task nei riquadri', x + 18, y + 80, 10, 'muted')
        yy = y + 99
        for index, step in enumerate(steps):
            step_card(b, step, x + 14, yy, w - 28, card_h, True)
            yy += card_h
            if index != len(steps) - 1:
                b.arrow(x + w / 2, yy + gap / 2, True)
                yy += gap
        return y + h
    h = 444
    b.rect(x, y, w, h, 'white', 10, 'line')
    section_header(b, 'Fasi procedurali', x, y, w, '1 / 4 fasi completate')
    b.text('Workflow: ' + wf.get('name', 'Gestione data breach') + '  ·  Sequenza ordinata',
           x + 20, y + 56, 11, 'muted')
    b.text('Descrizione del flusso in alto; task e comandi nella parte inferiore di ogni fase.',
           x + 20, y + 77, 10.5, 'muted')
    cw, gap = 278.5, 24
    for index, step in enumerate(steps):
        sx = x + 20 + index * (cw + gap)
        step_card(b, step, sx, y + 94, cw, 334)
        if index != len(steps) - 1:
            b.arrow(sx + cw + gap / 2, y + 94 + 167)
    return y + h


def field(b, label, value, x, y, w, h=36, size=12, select=False):
    b.text(label, x, y, 10, 'muted')
    b.rect(x, y + 8, w, h, 'white', 5, '#cbd7e2')
    max_w = w - 25 - (14 if select else 0)
    field_lines = lines(str(value), max_w, size)
    if len(field_lines) == 1:
        b.text(str(value), x + 11, y + 8 + h / 2 + size * .35, size, 'ink')
    else:
        b.para(value, x + 11, y + 25, max_w, size, 'ink', leading=16)
    if select:
        b.chevron(x + w - 15, y + 8 + h / 2)


def general_data(b, data, y, mobile=False):
    incident = data['incident']
    x, w = (16, 398) if mobile else (278, 1226)
    h = 556 if mobile else 374
    b.rect(x, y, w, h, 'white', 10, 'line')
    section_header(b, 'Dati generali', x, y, w)
    if mobile:
        field(b, 'Riferimento', incident['reference'], x + 18, y + 65, 175, 36, 11)
        field(b, 'Gravità', incident['severity'], x + 204, y + 65, 176, 36, 11, True)
        field(b, 'Stato', incident['status_label'], x + 18, y + 133, 175, 36, 11, True)
        field(b, 'Inizio violazione', home.fmt(incident['start_at']), x + 204, y + 133, 176, 36, 10.5)
        b.text('Descrizione', x + 18, y + 201, 10, 'muted')
        b.rect(x + 18, y + 209, w - 36, 89, 'white', 5, '#cbd7e2')
        b.para(incident['description'], x + 29, y + 229, w - 58, 10.4, 'ink', leading=15)
        b.line(x + 18, y + 312, x + w - 18, y + 312)
        b.text('Altri dati e campi personalizzati', x + 18, y + 339, 11, 'blue')
        b.chevron(x + w - 25, y + 334)
        b.text('Date, destinatari, classificazione, rischio e campi aggiuntivi', x + 18, y + 359, 8.7, 'muted')
        b.text('Categorie', x + 18, y + 391, 9, 'muted')
        b.text(' · '.join(incident['categories']), x + 18, y + 409, 10, '#2e4e68')
        b.text('Personale', x + 18, y + 434, 9, 'muted')
        b.text(incident['people'], x + 18, y + 452, 11, '#2e4e68')
        b.text('Dati interessati', x + 210, y + 434, 9, 'muted')
        b.text(' · '.join(incident['data_types']), x + 210, y + 452, 11, '#2e4e68')
        b.button('Label, personale e raccomandazioni', x + 18, y + 466, w - 36, 33, False, 10)
        b.button('Salva dati generali', x + 18, y + 510, w - 36, 33, True, 11)
        return y + h
    fw = (w - 94) / 4
    for index, (label, value, select) in enumerate([
            ('Riferimento', incident['reference'], False),
            ('Gravità', incident['severity'], True),
            ('Stato', incident['status_label'], True),
            ('Inizio violazione', home.fmt(incident['start_at']), False)]):
        field(b, label, value, x + 20 + index * (fw + 18), y + 65, fw, 36, 12, select)
    b.text('Descrizione', x + 20, y + 132, 10, 'muted')
    b.rect(x + 20, y + 140, w - 40, 61, 'white', 5, '#cbd7e2')
    b.para(incident['description'], x + 31, y + 162, w - 62, 11.5, 'ink', leading=17)
    b.line(x + 20, y + 215, x + w - 20, y + 215)
    b.text('Altri dati e campi personalizzati', x + 20, y + 241, 11, 'blue')
    b.text('Date, destinatari, classificazione, rischio e campi aggiuntivi', x + 292, y + 241, 10, 'muted')
    b.chevron(x + w - 25, y + 236)
    b.line(x + 20, y + 259, x + w - 20, y + 259)
    for label, value, xx in [
            ('Categorie', ' · '.join(incident['categories']), x + 20),
            ('Personale', incident['people'], x + 510),
            ('Dati interessati', ' · '.join(incident['data_types']), x + 900)]:
        b.text(label, xx, y + 279, 9.5, 'muted')
        b.text(value, xx, y + 299, 11, '#2e4e68')
    b.button('Label, personale e raccomandazioni', x + 20, y + 328, 282, 33, False, 10.5)
    b.button('Salva dati generali', x + w - 208, y + 328, 188, 33, True, 11)
    return y + h


def warning(b, data, y, mobile=False):
    x, w = (16, 398) if mobile else (278, 1226)
    h = 88 if mobile else 64
    b.rect(x, y, w, h, '#fff8e9', 8, '#ead6ac')
    b.rect(x + 17, y + 17, 24, 24, '#f6e4bc', 12)
    b.text('!', x + 29, y + 34, 12, '#916015', True, 'center')
    b.text('Avvisi procedurali · ' + str(len(data['workflow']['warnings'])), x + 52, y + 26, 12, '#7a541c', True)
    text = 'Azione richiesta da registrare e documento necessario alla notifica da generare.'
    b.para(text, x + 52, y + 46, w - 70, 10.8, '#866b3e', leading=16)
    return y + h


def desktop(c, data):
    b = Board(c, 1536, 1530, 'Desktop · dati dimostrativi')
    topbar(b, data)
    incident_header(b, data)
    b.pill(data['incident']['status_label'], 278, 276, '#fff3dc', '#875a17')
    b.pill('Gravità ' + data['incident'].get('severity', 'Alta').lower(), 349, 276, '#fff1e5', '#99551b')
    b.text('Inizio ' + home.fmt(data['incident']['start_at']), 455, 293, 10.5, 'muted')
    b.text('Durata ' + data['incident']['duration'], 642, 293, 10.5, 'muted')
    b.button('Report PDF', 1100, 270, 125, 38, False, 11.5)
    b.button('+ Registra azione', 1233, 270, 223, 38, True, 11.5)
    b.button('⋯', 1464, 270, 40, 38, False, 18)
    section_nav(b, data, 326)
    y = workflow(b, data, 394)
    y = warning(b, data, y + 18)
    y = general_data(b, data, y + 18)
    collapsed(b, 'Dati titolare e responsabile', 278, y + 18, 1226)
    collapsed(b, 'Conseguenze, misure e raccomandazioni', 278, y + 82, 1226)
    b.text('Azioni, promemoria, documenti, moduli e notifiche proseguono nella stessa pagina.',
           278, 1474, 11, 'muted')
    b.line(278, 1491, 1504, 1491)
    b.text('Cybersecurity Incident Registry · 0.9.0-1', 278, 1515, 9, '#8091a0')
    b.text('Proposta visiva · nessun dato reale', 1504, 1515, 9, '#61798d', anchor='right')
    b.end()


def mobile(c, data):
    b = Board(c, 430, 3300, 'Mobile')
    topbar(b, data, True)
    incident_header(b, data, 126, True)
    b.pill(data['incident']['status_label'], 16, 302, '#fff3dc', '#875a17', 10)
    b.pill('Gravità ' + data['incident'].get('severity', 'Alta').lower(), 158, 302, '#fff1e5', '#99551b', 10)
    b.text('Inizio ' + home.fmt(data['incident']['start_at']) + '  ·  Durata ' + data['incident']['duration'], 16, 347, 10, 'muted')
    b.button('Report PDF', 16, 363, 120, 40, False, 11)
    b.button('+ Registra azione', 144, 363, 222, 40, True, 11.5)
    b.button('⋯', 374, 363, 40, 40, False, 18)
    section_nav(b, data, 419, True)
    y = workflow(b, data, 593, True)
    y = warning(b, data, y + 16, True)
    y = general_data(b, data, y + 16, True)
    for title in ['Dati titolare e responsabile', 'Conseguenze, misure e raccomandazioni',
                  'Azioni', 'Promemoria specifici', 'Documenti', 'Generazione moduli', 'Notifiche']:
        y += 12
        collapsed(b, title, 16, y, 398, h=48)
        y += 48
    b.line(16, y + 22, 414, y + 22)
    b.text('CIR 0.9.0-1 · Dati dimostrativi', 16, y + 46, 9, '#8091a0')
    b.text('Stessa pagina · sezioni espandibili', 414, y + 46, 8.5, '#61798d', anchor='right')
    if y + 60 > b.h:
        raise ValueError(f'Mobile page requires {y + 60}px, available {b.h}')
    b.end()


def operations(c, data):
    b = Board(c, 1536, 1480, 'Desktop · sezioni operative della stessa pagina')
    topbar(b, data)
    incident_header(b, data, compact=True)
    x, w = 278, 1226
    section_nav(b, data, 251, compact=True)
    b.rect(x, 298, w, 287, 'white', 10, 'line')
    section_header(b, 'Azioni', x, 298, w, '2 registrazioni dimostrative')
    b.button('+ Aggiungi azione', x + w - 191, 356, 171, 37, True, 11)
    b.text('Registro delle attività dell’incidente', x + 20, 379, 11, 'muted')
    for index, row in enumerate(data['actions']):
        yy = 413 + index * 73
        b.line(x + 20, yy - 7, x + w - 20, yy - 7, '#e1e8ef')
        b.text(home.fmt(row['when_at']), x + 20, yy + 17, 10.5, 'muted')
        b.text(row['label'], x + 198, yy + 17, 12, 'ink', True)
        b.para(row['description'], x + 198, yy + 39, 720, 11, 'muted', leading=15)
        b.button('Apri / modifica', x + w - 152, yy + 4, 132, 33, False, 10.5)
    b.rect(x, 603, w, 83, 'white', 10, 'line')
    section_header(b, 'Promemoria specifici', x, 603, w)
    reminder = data['reminders'][0]
    b.text(home.fmt(reminder['scheduled_at']) + ' · ' + reminder['message'], x + 20, 665, 10.5, 'muted')
    b.button('+ Aggiungi promemoria', x + w - 226, 642, 206, 31, False, 10.5)
    b.rect(x, 704, w, 265, 'white', 10, 'line')
    section_header(b, 'Documenti', x, 704, w)
    b.button('+ Carica documenti', x + 20, 758, 175, 37, True, 11)
    b.rect(x + 208, 758, 229, 37, 'white', 6, '#c9d6e2')
    b.text('Destinazione: CIR + Alfresco', x + 220, 782, 11)
    b.chevron(x + 421, 776)
    b.button('Sync Alfresco', x + 449, 758, 142, 37, False, 11)
    b.text('Verifica lo stato remoto', x + 606, 782, 10, 'muted')
    ty = 816
    b.rect(x + 20, ty, w - 40, 34, '#eef3f7', 5)
    headers = [('Documento', 34), ('Tag di notifica', 496), ('Archiviazione', 738), ('Operazioni', 1000)]
    for label, xx in headers:
        b.text(label, x + xx, ty + 22, 10, '#587086', True)
    for index, row in enumerate(data['documents']):
        yy = ty + 34 + index * 48
        b.line(x + 20, yy + 47, x + w - 20, yy + 47, '#e2e9ef')
        b.icon('file', x + 33, yy + 15, 17, '#6c8ba2')
        b.text(row['name'], x + 60, yy + 30, 11.5, '#24517d', True)
        tags = row['tags']
        if isinstance(tags, list):
            tags = ', '.join(tags)
        b.text(tags or 'Nessun tag assegnato', x + 496, yy + 30, 10.5, 'muted')
        b.text(row['storage'], x + 738, yy + 30, 10.5, 'muted')
        b.button('Scarica', x + 1000, yy + 9, 77, 31, False, 10)
        b.button('Altre azioni', x + 1086, yy + 9, 99, 31, False, 10)
    b.rect(x, 987, w, 150, 'white', 10, 'line')
    section_header(b, 'Generazione moduli', x, 987, w)
    b.rect(x + 20, 1044, w - 229, 41, 'white', 5, '#cbd7e2')
    b.check(x + 32, 1058, True, 14)
    b.text(data['forms'][0]['title'], x + 55, 1072, 12)
    b.text('Template del workflow', x + 638, 1071, 10.5, 'muted')
    b.button('Genera documenti', x + w - 194, 1045, 174, 40, True, 11)
    b.text('Altro modello disponibile: ' + data['forms'][1]['title'], x + 20, 1115, 10.5, 'muted')
    b.rect(x, 1155, w, 234, 'white', 10, 'line')
    section_header(b, 'Notifiche', x, 1155, w)
    b.text('Verifica destinatari, testo e allegati nell’anteprima prima dell’invio.', x + 20, 1217, 11, 'muted')
    for index, row in enumerate(data['notifications']):
        nx = x + 20 + index * 602
        b.rect(nx, 1235, 584, 133, '#f9fbfd', 8, '#d7e2ec')
        b.text(row['title'], nx + 16, 1261, 12, 'ink', True)
        b.text(row['description'], nx + 16, 1286, 10.5, 'muted')
        b.button(row['button'], nx + 16, 1308, 220, 38, row['ready'], 11)
        if not row['ready']:
            b.text('Documento da generare', nx + 254, 1332, 10, '#8b5c13')
    b.line(x, 1427, x + w, 1427)
    b.text('Cybersecurity Incident Registry · 0.9.0-1', x, 1452, 9, '#8091a0')
    b.text('Proposta visiva · comandi locali dimostrativi', x + w, 1452, 9, '#61798d', anchor='right')
    b.end()


def standalone(output):
    html = (HERE / 'index.html').read_text()
    css = (HERE / 'styles.css').read_text()
    js = (HERE / 'incident.js').read_text()
    assert '<link rel="stylesheet" href="styles.css">' in html
    assert '<script src="incident.js" defer></script>' in html
    html = html.replace('<link rel="stylesheet" href="styles.css">', '<style>' + css + '</style>')
    html = html.replace('<script src="incident.js" defer></script>', '')
    html = html.replace('</body>', '<script>' + js + '</script></body>')
    html = html.replace('../../visual-assets/cybersecurity-hero-v2.png',
                        'data:image/png;base64,' + base64.b64encode(PHOTO.read_bytes()).decode())
    html = html.replace('../../../app/static/cir-application-logo.svg',
                        'data:image/svg+xml;base64,' + base64.b64encode(LOGO.read_bytes()).decode())
    assert '../../visual-assets/' not in html
    assert '../../../app/static/' not in html
    assert not re.search(r'<(?:script|link)[^>]+(?:src|href)=["\'](?!data:)', html)
    (output / 'CIR_Incident_v1.html').write_text(html)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--boards-only', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data = json.loads((HERE / 'fixtures.json').read_text())
    target = args.output / 'CIR_Incident_v1.pdf'
    c = canvas.Canvas(str(target), invariant=1)
    c.setTitle('Cybersecurity Incident Registry - Mockup dettaglio incidente')
    c.setAuthor('Cybersecurity Incident Registry')
    desktop(c, data)
    mobile(c, data)
    operations(c, data)
    c.save()
    pdf = fitz.open(target)
    names = ['CIR_Incident_v1_Desktop.png', 'CIR_Incident_v1_Mobile.png', 'CIR_Incident_v1_Operations.png']
    for page, name in zip(pdf, names):
        page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).save(args.output / name)
    if not args.boards_only:
        standalone(args.output)
    metadata = {
        'scope': 'isolated_incident_detail_mock_only',
        'approval': 'pending_incident_detail_approval',
        'approved_login_and_home_changed': False,
        'application_runtime_changed': False,
        'native_design_boards_not_browser_screenshots': True,
        'functional_version': '0.9.0-1',
        'pages': 3,
        'dimensions': [[round(p.rect.width), round(p.rect.height)] for p in pdf],
        'demo_incident': data['incident'],
        'data_source': 'docs/design/incident-v1/fixtures.json',
        'photo_asset': str(PHOTO.relative_to(ROOT)),
        'photo_sha256': hashlib.sha256(PHOTO.read_bytes()).hexdigest(),
        'layout': {'workflow': 'numbered two-part blocks; flow description above task/action',
                   'desktop_arrows': 'horizontal', 'mobile_arrows': 'vertical',
                   'operations_board': 'lower sections of same incident page'},
        'dependencies': ['ReportLab', 'PyMuPDF', 'Pillow', 'local DejaVu fonts'],
        'text_count': len(DRAWING_LOG),
        'source_hashes': {
            name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
            for name in ['fixtures.json', 'styles.css', 'incident.js', 'index.html', 'render_incident.py']
        },
    }
    (args.output / 'incident-v1-metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    (args.output / 'incident-v1-text-geometry.json').write_text(json.dumps(DRAWING_LOG, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
