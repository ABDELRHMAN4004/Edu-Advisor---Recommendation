"""Shared services converted from the supplied Streamlit application."""
from __future__ import annotations
from collections import defaultdict
from html import escape
from io import BytesIO
import re
from typing import Any
from pypdf import PdfReader

BIDI = dict.fromkeys(map(ord, '\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff\u2066\u2067\u2068\u2069'), None)
SEMESTERS = {1: 'Fall', 2: 'Spring', 3: 'Summer'}

def normalize_course_code(value: str) -> str:
    return re.sub(r'[^A-Z0-9]', '', str(value).upper().translate(BIDI))

def course_display(advisor, course_id: str) -> str:
    row = advisor.courses.loc[course_id]
    names = []
    for name in (row.get('Course_Name_Arabic'), row.get('Course_Name')):
        name = str(name or '').strip()
        if name and name.casefold() not in {'nan', 'none', 'null'} and name not in names:
            names.append(name)
    return ' / '.join(names) or course_id

def extract_course_attempts(page_texts: list[str], catalog_course_ids: list[str]) -> list[dict]:
    catalog = {normalize_course_code(cid): cid for cid in catalog_course_ids}
    generic = re.compile(r'(?<![A-Z0-9])([A-Z]{1,8})[\s._/-]*([0-9]{2,5})([A-Z]?)(?![A-Z0-9])', re.I)
    attempts = []
    for page_number, page_text in enumerate(page_texts, 1):
        pending_status = None
        for line_number, raw_line in enumerate((page_text or '').splitlines(), 1):
            line = raw_line.translate(BIDI).upper().strip()
            compact = re.sub(r'[^A-Z0-9¥]', '', line)
            if compact == 'X':
                pending_status = 'failed'
                continue
            if compact in {'Y', '¥'}:
                pending_status = 'passed'
                continue
            inline_status = None
            if generic.search(line) and re.search(r'(^|[^A-Z0-9])X([^A-Z0-9]|$)', line):
                inline_status = 'failed'
            elif generic.search(line) and '¥' in line:
                inline_status = 'passed'
            found = []
            for match in generic.finditer(line):
                code = normalize_course_code(''.join(match.groups()))
                if code and code not in found:
                    found.append(code)
            if not found:
                for normalized in catalog:
                    if normalized and re.search(r'(?<![A-Z0-9])' + r'[\s._/-]*'.join(map(re.escape, normalized)) + r'(?![A-Z0-9])', line):
                        found.append(normalized)
            if not found:
                continue
            for code in found:
                attempts.append({'course_code_normalized': code, 'course_id': catalog.get(code), 'status': inline_status or pending_status or 'unknown', 'page': page_number, 'line': line_number, 'sequence': len(attempts) + 1})
            pending_status = None
    return attempts

def repeated_failure_advisories(attempts: list[dict], advisor) -> list[dict]:
    grouped = defaultdict(list)
    for attempt in attempts:
        if attempt.get('course_id') and attempt.get('status') in {'passed', 'failed', 'unknown'}:
            grouped[attempt['course_id']].append(attempt)
    result = []
    for cid, history in grouped.items():
        history.sort(key=lambda x: x.get('sequence', 0))
        failures = sum(a['status'] == 'failed' for a in history)
        if failures >= 2 and history[-1]['status'] == 'failed' and cid in advisor.courses.index:
            result.append({'course_id': cid, 'course_name': course_display(advisor, cid), 'failed_attempts': failures})
    return sorted(result, key=lambda x: (-x['failed_attempts'], x['course_id']))

def extract_transcript(pdf: bytes, advisor) -> dict:
    reader = PdfReader(BytesIO(pdf))
    page_texts = [page.extract_text() or '' for page in reader.pages]
    full_text = '\n'.join(page_texts)
    attempts = extract_course_attempts(page_texts, sorted(advisor.all_courses))
    # Preserve the source app's heuristic: second-to-last 3-decimal number = cumulative GPA.
    gpa_values = [float(x) for x in re.findall(r'(?<![\d.])(\d*\.\d{3})(?!\d)', full_text)]
    cumulative_gpa = gpa_values[-2] if len(gpa_values) >= 2 else (gpa_values[-1] if gpa_values else None)
    term_gpa = gpa_values[-1] if len(gpa_values) >= 2 else None
    latest = {}
    for attempt in attempts:
        if attempt['course_id'] and attempt['status'] in {'passed', 'failed'}:
            latest[attempt['course_id']] = attempt['status']
    passed = sorted(cid for cid, status in latest.items() if status == 'passed')
    failed = sorted(cid for cid, status in latest.items() if status == 'failed')
    counts = defaultdict(lambda: {'failed': 0, 'passed': 0})
    for a in attempts:
        if a['course_id'] and a['status'] in {'passed', 'failed'}:
            counts[a['course_id']][a['status']] += 1
    return {
        'attempts': attempts, 'passed_courses': passed, 'failed_courses': failed,
        'cumulative_gpa': cumulative_gpa, 'latest_term_gpa': term_gpa,
        'passed_hours': sum(int(advisor.courses.loc[c, 'Credits']) for c in passed),
        'failed_hours': sum(int(advisor.courses.loc[c, 'Credits']) for c in failed),
        'unmatched_codes': sorted({a['course_code_normalized'] for a in attempts if not a['course_id'] or a['status'] == 'unknown'}),
        'attempt_counts': [{'course_id': cid, 'course_name': course_display(advisor, cid), 'failed_attempts': c['failed'], 'passed_attempts': c['passed'], 'latest_status': latest.get(cid, 'unknown')} for cid, c in sorted(counts.items())],
        'repeated_failure_advisories': repeated_failure_advisories(attempts, advisor),
        'page_count': len(page_texts), 'text_detected': bool(full_text.strip()),
        'review_warning': 'PDF extraction is heuristic. Scanned PDFs need OCR; check codes, statuses and GPA before use.'
    }

def percentage_to_grade_points(score: float) -> float:
    for threshold, points in [(90,4.0),(85,3.7),(80,3.3),(75,3.0),(70,2.7),(65,2.3),(60,2.0),(55,1.7),(50,1.0)]:
        if score >= threshold:
            return points
    return 0.0

def calculate_gpa(advisor, grades: list[dict], previous_gpa: float = 0.0, previous_hours: int = 0) -> dict:
    quality = weighted_percentage = 0.0
    hours = 0
    rows = []
    for item in grades:
        cid, score = item['course_id'], float(item['score'])
        credits = int(advisor.courses.loc[cid, 'Credits'])
        points = percentage_to_grade_points(score)
        quality += credits * points
        weighted_percentage += credits * score
        hours += credits
        rows.append({'course_id': cid, 'course_name': course_display(advisor, cid), 'credits': credits, 'numerical_grade': score, 'gpa_points': points, 'quality_points': credits * points})
    semester_gpa = quality / hours if hours else None
    cumulative = (previous_gpa * previous_hours + quality) / (previous_hours + hours) if previous_hours + hours else None
    return {'courses': rows, 'semester_gpa': semester_gpa, 'semester_average_percentage': weighted_percentage / hours if hours else None, 'semester_credit_hours': hours, 'total_quality_points': quality, 'estimated_cumulative_gpa': cumulative, 'total_credit_hours': previous_hours + hours, 'note': 'Uses the percentage-to-points mapping from the supplied Streamlit code; official repeat-course rules may change the result.'}

def recommendations_pdf(result: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=12*mm, leftMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='EduTitle', parent=styles['Title'], alignment=TA_CENTER, fontSize=17))
    styles.add(ParagraphStyle(name='EduCell', parent=styles['BodyText'], fontSize=7, leading=9, wordWrap='CJK'))
    story = [Paragraph('Edu Advisor - Course Recommendation Report', styles['EduTitle']), Spacer(1, 4*mm)]
    student, status = result.get('student', {}), result.get('status', {})
    gpa = student.get('gpa')
    summary = [['Current GPA', f'{gpa:.3f}' if isinstance(gpa,(int,float)) else 'N/A', 'Academic Year', str(student.get('current_level','N/A'))], ['Passed Hours', str(status.get('total_passed_hours',0)), 'Failed Hours', str(status.get('total_failed_hours',0))], ['Eligible Courses', str(status.get('candidates_found',0)), 'Recommended Courses', str(len(result.get('recommendations',[])))]]
    t = Table(summary, colWidths=[35*mm,35*mm,40*mm,35*mm]);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.grey),('BACKGROUND',(0,0),(0,-1),colors.whitesmoke),('BACKGROUND',(2,0),(2,-1),colors.whitesmoke)]))
    story.extend([t, Spacer(1,5*mm)])
    headers = ['#','Course Code','Course Name (Arabic / English)','Credits','Type','Category','Retake','Reasons']
    table_data = [[Paragraph(escape(x), styles['EduCell']) for x in headers]]
    failed_rows = []
    for i, rec in enumerate(result.get('recommendations',[]),1):
        failed = bool(rec.get('is_retake')) or rec.get('course_id') in status.get('failed_course_ids',[])
        values = [i,rec.get('course_id',''),rec.get('course_name_display',rec.get('course_name','')),rec.get('credits',''),rec.get('type',''),rec.get('category',''),'Yes' if failed else 'No',' | '.join(map(str,rec.get('reasons',[])))]
        table_data.append([Paragraph(escape(str(v)),styles['EduCell']) for v in values])
        if failed: failed_rows.append(i)
    table = Table(table_data, colWidths=[10*mm,23*mm,58*mm,14*mm,20*mm,28*mm,13*mm,100*mm], repeatRows=1)
    commands=[('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.35,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP')]
    commands += [('BACKGROUND',(0,i),(-1,i),colors.HexColor('#FDE2E2')) for i in failed_rows]
    table.setStyle(TableStyle(commands));story.extend([table,Spacer(1,4*mm),Paragraph('Review against official academic regulations before registration.',styles['Italic'])]);doc.build(story)
    return output.getvalue()
