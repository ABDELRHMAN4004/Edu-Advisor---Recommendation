from pathlib import Path
from io import BytesIO
from html import escape
import re
import pandas as pd
import streamlit as st
from pypdf import PdfReader
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    )
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
from recommender import EduAdvisor, create_student_input
# Documentation: https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/streamlit_app/normalize_course_code.txt
def normalize_course_code(value: str) -> str:
    value = str(value).upper()
    value = value.translate(dict.fromkeys(map(
        ord,
        "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff\u2066\u2067\u2068\u2069"
    ), None))
    return re.sub(r"[^A-Z0-9]", "", value)
# Documentation: https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/streamlit_app/extract_course_attempts.txt
def extract_course_attempts(page_texts, catalog_course_ids):
    catalog_by_normalized_id = {
        normalize_course_code(cid): cid for cid in catalog_course_ids
    }
    generic_code_pattern = re.compile(
        r"(?<![A-Z0-9])([A-Z]{1,8})[\s.\_/-]\*([0-9]{2,5})([A-Z]?)(?![A-Z0-9])",
        re.IGNORECASE,
    )
    bidi_chars = dict.fromkeys(map(
        ord,
        "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff\u2066\u2067\u2068\u2069"
    ), None)
    attempts = []
    for page_number, page_text in enumerate(page_texts, start=1):
        pending_status = None
        for line_number, raw_line in enumerate(
            (page_text or "").splitlines(), start=1
        ):
            line = raw_line.translate(bidi_chars).upper().strip()
            compact = re.sub(r"[^A-Z0-9¥]", "", line)
            if compact == "X":
                pending_status = "failed"
                continue
            if compact in {"¥", "Y"}:
                pending_status = "passed"
                continue
            inline_status = None
            has_code_on_line = bool(generic_code_pattern.search(line))
            if has_code_on_line and re.search(
                r"(^|[^A-Z0-9])X([^A-Z0-9]|$)", line
            ):
                inline_status = "failed"
            elif has_code_on_line and "¥" in line:
                inline_status = "passed"
            found = []
            for match in generic_code_pattern.finditer(line):
                normalized = normalize_course_code("".join(match.groups()))
                if normalized and normalized not in found:
                    found.append(normalized)
            if not found:
                for normalized_catalog in catalog_by_normalized_id:
                    if not normalized_catalog:
                        continue
                    flexible = r"[\s.\_/-]\*".join(
                        map(re.escape, normalized_catalog)
                    )
                    if re.search(
                        rf"(?<![A-Z0-9]){flexible}(?![A-Z0-9])",
                        line,
                    ):
                        found.append(normalized_catalog)
            if not found:
                continue
            for normalized in found:
                attempts.append({
                    "course_code_normalized": normalized,
                    "course_id": catalog_by_normalized_id.get(normalized),
                    "status": inline_status or pending_status or "unknown",
                    "page": page_number,
                    "line": line_number,
                    "sequence": len(attempts) + 1,
                })
            pending_status = None
    return attempts
def get_repeated_failure_advisories(attempt_records):
    """Find courses failed at least twice where the latest attempt is failed."""
    attempts_by_course = {}
    for attempt in attempt_records or []:
        course_id = attempt.get("course_id")
        status = attempt.get("status")
        if not course_id or status not in {"passed", "failed", "unknown"}:
            continue
        attempts_by_course.setdefault(course_id, []).append(attempt)
    advisories = []
    for course_id, attempts in attempts_by_course.items():
        attempts.sort(key=lambda item: item.get("sequence", 0))
        failed_count = sum(
            attempt.get("status") == "failed"
            for attempt in attempts
        )
        latest_status = attempts[-1].get("status")
        # Do not advise against retaking a course if the latest
        # recorded attempt is passed or its status is unknown.
        if failed_count >= 2 and latest_status == "failed":
            if course_id not in advisor.courses.index:
                continue
            advisories.append({
                "course_id": course_id,
                "course_name": bilingual_course_name(course_id),
                "failed_attempts": failed_count,
            })
    return sorted(
        advisories,
        key=lambda item: (-item["failed_attempts"], item["course_id"]),
    )
st.set_page_config(
    page_title="Edu Advisor | Course Recommendation",
    layout="wide",
)
PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
@st.cache_resource
# Documentation: https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/streamlit_app/load_advisor.txt
def load_advisor():
    return EduAdvisor(data_dir=DATA_DIR)
def _clean_course_name(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if not text or text.casefold() in {
        "nan", "none", "null"
    } else text
def bilingual_course_name(course_id: str) -> str:
    row = advisor.courses.loc[course_id]
    english = _clean_course_name(
        row.get("Course_Name", row.get("name_en", row.get("name", "")))
    )
    arabic = _clean_course_name(
        row.get(
            "Course_Name_Arabic",
            row.get(
                "name_ar",
                row.get("arabic_name", row.get("name_arabic", "")),
            ),
        )
    )
    names = []
    for name in (arabic, english):
        if name and name not in names:
            names.append(name)
    return " / ".join(names) if names else course_id
# Documentation: https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/streamlit_app/course_label.txt
def course_label(course_id: str) -> str:
    row = advisor.courses.loc[course_id]
    return (
        f"{course_id} — {bilingual_course_name(course_id)} "
        f"({int(row['Credits'])} credits)"
    )
# Documentation: https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/streamlit_app/build_recommendations_pdf.txt
def build_recommendations_pdf(result: dict) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError(
            "PDF export requires reportlab. Install it with: pip install reportlab"
        )
    student = result.get("student", {})
    status = result.get("status", {})
    recommendations = result.get("recommendations", [])
    failed_course_ids = set(status.get("failed_course_ids", []))
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="Edu Advisor Course Recommendations",
        author="Edu Advisor",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=21,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="SmallCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9,
        alignment=TA_LEFT,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="SmallHeader",
        parent=styles["SmallCell"],
        fontName="Helvetica-Bold",
        textColor=colors.white,
    ))
    styles.add(ParagraphStyle(
        name="FailedCell",
        parent=styles["SmallCell"],
        textColor=colors.HexColor("#B91C1C"),
        fontName="Helvetica-Bold",
    ))
    story = [
        Paragraph("Edu Advisor", styles["ReportTitle"]),
        Paragraph("Course Recommendation Report", styles["Heading2"]),
        Spacer(1, 3 * mm),
    ]
    gpa = student.get("gpa")
    summary_rows = [
        [
            "Current GPA",
            f"{gpa:.3f}" if isinstance(gpa, (int, float)) else "N/A",
            "Academic Year",
            str(student.get("current_level", "N/A")),
        ],
        [
            "Total Passed Hours",
            str(status.get(
                "total_passed_hours",
                student.get("completed_credits", 0),
            )),
            "Eligible Courses",
            str(status.get(
                "candidates_found",
                len(recommendations),
            )),
        ],
        [
            "Total Failed Hours",
            str(status.get(
                "total_failed_hours",
                status.get("failed_credits", 0),
            )),
            "Recommended Courses",
            str(len(recommendations)),
        ],
        [
            "Minimum Required Hours",
            str(status.get("minimum_credits_required", 12)),
            "Maximum Allowed Hours",
            str(status.get("maximum_credits_allowed", 18)),
        ],
    ]
    summary_table = Table(
        summary_rows,
        colWidths=[35 * mm, 35 * mm, 40 * mm, 35 * mm],
    )
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E9EEF5")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#E9EEF5")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C2CC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([
        summary_table,
        Spacer(1, 6 * mm),
        Paragraph("Recommended Courses", styles["Heading2"]),
        Spacer(1, 2 * mm),
    ])
    headers = [
        "#",
        "Course Code",
        "Course Name (Arabic / English)",
        "Credits",
        "Type",
        "Category",
        "Retake",
        "Recommendation Reasons",
    ]
    table_data = [
        [Paragraph(escape(h), styles["SmallHeader"]) for h in headers]
    ]
    failed_row_indices = []
    for rec in recommendations:
        cid = rec.get("course_id")
        is_failed = (
            cid in failed_course_ids
            or bool(rec.get("is_retake", False))
        )
        cell_style = styles["FailedCell"] if is_failed else styles["SmallCell"]
        values = [
            rec.get("rank", ""),
            cid or "",
            rec.get("course_name_display", rec.get("course_name", "")),
            rec.get("credits", ""),
            rec.get("type", ""),
            rec.get("category", ""),
            "Yes" if is_failed else "No",
            "<br/>".join(
                escape(str(reason)) for reason in rec.get("reasons", [])
            ) or "-",
        ]
        table_data.append([
            Paragraph(escape(str(value)), cell_style)
            for value in values
        ])
        if is_failed:
            failed_row_indices.append(len(table_data) - 1)
    rec_table = Table(
        table_data,
        colWidths=[
            10 * mm,
            23 * mm,
            58 * mm,
            14 * mm,
            20 * mm,
            28 * mm,
            13 * mm,
            100 * mm,
        ],
        repeatRows=1,
        hAlign="LEFT",
    )
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243447")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B8C2CC")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#F5F7FA")
        ]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for row_index in failed_row_indices:
        table_style.append((
            "BACKGROUND",
            (0, row_index),
            (-1, row_index),
            colors.HexColor("#FDE2E2"),
        ))
    rec_table.setStyle(TableStyle(table_style))
    story.extend([
        rec_table,
        Spacer(1, 4 * mm),
        Paragraph(
            "Review these recommendations against the official academic "
            "regulations before registration.",
            styles["Italic"],
        ),
    ])
    document.build(story)
    return buffer.getvalue()
# Documentation: https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/streamlit_app/display_recommendations.txt
def display_recommendations(result: dict):
    student = result.get("student", {})
    status = result.get("status", {})
    recs = result.get("recommendations", [])
    gpa = student.get("gpa")
    minimum_hours = int(status.get("minimum_credits_required", 12))
    maximum_hours = int(status.get("maximum_credits_allowed", 18))
    failed_course_ids = set(status.get("failed_course_ids", []))
    st.subheader("Credit Hour Registration Requirements")
    if gpa is not None and float(gpa) < 2.0:
        st.warning(
            f"Your cumulative GPA is below 2.00. "
            f"You must register for at least {minimum_hours} credit hours."
        )
    else:
        st.info(
            f"You can register for a minimum of {minimum_hours} "
            f"and a maximum of {maximum_hours} credit hours."
        )
    st.caption(
        "Credit-hour requirements should be verified against the official "
        "university bylaws."
    )
    st.subheader("Student Summary")
    cols = st.columns(4)
    cols[0].metric(
        "Current GPA",
        f"{float(gpa):.2f}" if gpa is not None else "N/A",
    )
    cols[1].metric(
        "Academic year",
        student.get("current_level", "N/A"),
    )
    cols[2].metric(
        "Total Passed Hours",
        status.get(
            "total_passed_hours",
            student.get("completed_credits", 0),
        ),
    )
    cols[3].metric(
        "Total Failed Hours",
        status.get(
            "total_failed_hours",
            status.get("failed_credits", 0),
        ),
    )
    status_cols = st.columns(2)
    status_cols[0].metric(
        "Eligible courses",
        status.get("candidates_found", 0),
    )
    if status.get("academic_warning"):
        status_cols[1].warning(
            "The GPA is below the minimum required by the academic regulations."
        )
    else:
        status_cols[1].success(
            "No academic warning based on the entered GPA."
        )
    repeated_failures = status.get(
        "repeated_failure_advisories", []
    )
    if repeated_failures:
        st.subheader("Academic Advisory — Repeated Course Failure")
        st.warning(
            "Some courses have been failed multiple times. "
            "Consider discussing the next registration decision "
            "with the academic advisor."
        )
        for item in repeated_failures:
            st.markdown(
                f"- **{item['course_id']} — {item['course_name']}**: "
                f"Failed {item['failed_attempts']} times. "
                "Consider whether retaking this course in the current "
                "semester is appropriate."
            )
    st.subheader("Recommended Courses")
    if not recs:
        st.info(
            "No suitable courses were found for the current inputs and credit limits."
        )
        return
    rows = []
    for index, rec in enumerate(recs, start=1):
        cid = rec.get("course_id")
        is_failed = (
            cid in failed_course_ids
            or bool(rec.get("is_retake", False))
        )
        rows.append({
            "#": index,
            "Course Code": cid,
            "Course Name (Arabic / English)": rec.get(
                "course_name_display",
                rec.get("course_name"),
            ),
            "Credits": rec.get("credits"),
            "Type": rec.get("type"),
            "Category": rec.get("category"),
            "Retake": "Mandatory" if is_failed else "No",
            "Recommendation Reasons": " | ".join(
                rec.get("reasons", [])
            ),
            "_is_failed": is_failed,
        })
    recommendations_df = pd.DataFrame(rows)
    def highlight_failed_rows(row):
        if row["_is_failed"]:
            return [
                "background-color: #FDE2E2; color: #9B1C1C; font-weight: bold"
            ] * len(row)
        return [""] * len(row)
    styled_recommendations = recommendations_df.style.apply(
        highlight_failed_rows,
        axis=1,
    )
    visible_columns = [
        column
        for column in recommendations_df.columns
        if column != "_is_failed"
    ]
    st.dataframe(
        styled_recommendations,
        column_order=visible_columns,
        use_container_width=True,
        hide_index=True,
    )
    recommended_hours = sum(
        int(rec.get("credits", 0) or 0)
        for rec in recs
    )
    st.metric(
        "Total Recommended Credit Hours",
        recommended_hours,
    )
    if recommended_hours < minimum_hours:
        st.warning(
            f"The current recommendations total {recommended_hours} credit hours, "
            f"which is below the required minimum of {minimum_hours}. "
            "Review the available courses or the student's academic record."
        )
    if recommended_hours > maximum_hours:
        st.warning(
            f"The current recommendations total {recommended_hours} credit hours, "
            f"which exceeds the allowed maximum of {maximum_hours}. "
            "Review the recommendations before registration."
        )
    if REPORTLAB_AVAILABLE:
        try:
            pdf_bytes = build_recommendations_pdf(result)
            st.download_button(
                "Download Recommendations as PDF",
                data=pdf_bytes,
                file_name="edu_advisor_recommendations.pdf",
                mime="application/pdf",
                key="download_recommendations_pdf",
            )
        except Exception as exc:
            st.error(f"Could not generate the recommendations PDF: {exc}")
    else:
        st.warning(
            "PDF export is unavailable. Install the required package with: "
            "pip install reportlab"
        )
    with st.expander("View Full Result Details"):
        st.json(result)
# ---------------------------------------------------------------------
# Initialize application
# ---------------------------------------------------------------------
st.title("Edu Advisor")
st.caption(
    "Course Recommendation System — Fayoum University, "
    "Faculty of Computers and Information"
)
st.write(
    "A Streamlit test interface for evaluating recommendations "
    "before integrating with FastAPI."
)
if not DATA_DIR.exists():
    st.error(f"Data directory not found: `{DATA_DIR}`")
    st.info(
        "Place bylaws_courses.json, bylaws_prerequisites.json, "
        "and bylaws_rules.json in the project data directory."
    )
    st.stop()
try:
    advisor = load_advisor()
except Exception as exc:
    st.error("Could not load the recommendation engine or JSON files.")
    st.exception(exc)
    st.stop()
if advisor.courses.empty:
    st.error("The course catalog is empty.")
    st.stop()
all_course_ids = sorted(advisor.all_courses)
course_names = {
    cid: f"{cid} — {bilingual_course_name(cid)}"
    for cid in all_course_ids
}
semester_names = {
    1: "Fall",
    2: "Spring",
    3: "Summer",
}
semester_options = [1, 2, 3]
tab_recommend, tab_gpa, tab_catalog, tab_rules = st.tabs([
    "Recommendations",
    "GPA Calculator",
    "Course Catalog",
    "Academic Rules",
])
# ---------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------
with tab_recommend:
    st.header("Student Academic Information")
    st.subheader(
        "How would you like to enter the student's academic record?"
    )
    entry_method = st.radio(
        "Choose an input method",
        ["Upload transcript / statement", "Enter courses manually"],
        horizontal=True,
        key="academic_record_entry_method",
        help=(
            "Upload a PDF statement to extract the student's course history "
            "and GPA, or enter passed and failed courses manually. "
            "Academic year, semesters, and specialization must be selected manually."
        ),
    )
    if entry_method == "Upload transcript / statement":
        st.subheader("Upload Transcript PDF (Optional)")
        st.caption(
            "The PDF reader extracts course attempts, pass/fail statuses, "
            "and GPA when available. The student must manually choose the "
            "academic year, last completed semester, target semester, and specialization."
        )
        uploaded_pdf = st.file_uploader(
            "Choose a transcript PDF",
            type=["pdf"],
            key="student_statement_pdf",
        )
        if uploaded_pdf is not None:
            if st.button(
                "Extract Courses from Transcript",
                key="extract_pdf_courses",
            ):
                try:
                    reader = PdfReader(uploaded_pdf)
                    page_texts = [
                        page.extract_text() or ""
                        for page in reader.pages
                    ]
                    pdf_text = "\n".join(page_texts)
                    attempt_records = extract_course_attempts(
                        page_texts,
                        all_course_ids,
                    )
                    st.session_state["pdf_raw_text"] = pdf_text
                    if not attempt_records:
                        st.warning(
                            "No course codes were found in extractable PDF text. "
                            "The PDF may be scanned or use a different code format."
                        )
                    gpa_values = [
                        float(value)
                        for value in re.findall(
                            r"(?<![\d.])(\d\*\.\*\d{3})(?!\d)",
                            pdf_text,
                        )
                    ]
                    latest_cumulative_gpa = (
                        gpa_values[-2]
                        if len(gpa_values) >= 2
                        else (
                            gpa_values[-1]
                            if gpa_values
                            else None
                        )
                    )
                    latest_term_gpa = (
                        gpa_values[-1]
                        if len(gpa_values) >= 2
                        else None
                    )
                    last_status_by_code = {}
                    for attempt in attempt_records:
                        if (
                            attempt["course_id"]
                            and attempt["status"] in {"passed", "failed"}
                        ):
                            last_status_by_code[attempt["course_id"]] = (
                                attempt["status"]
                            )
                    extracted_passed = sorted(
                        cid
                        for cid, status in last_status_by_code.items()
                        if status == "passed"
                    )
                    extracted_failed = sorted(
                        cid
                        for cid, status in last_status_by_code.items()
                        if status == "failed"
                    )
                    st.session_state["pdf_attempt_records"] = attempt_records
                    st.session_state["pdf_detected_passed"] = extracted_passed
                    st.session_state["pdf_detected_failed"] = extracted_failed
                    st.session_state["pdf_unmatched_codes"] = sorted({
                        attempt["course_code_normalized"]
                        for attempt in attempt_records
                        if (
                            not attempt["course_id"]
                            or attempt["status"] == "unknown"
                        )
                    })
                    # Do not auto-fill the academic year, semesters,
                    # or specialization from the PDF.
                    if latest_cumulative_gpa is not None:
                        st.session_state["pdf_detected_gpa"] = (
                            latest_cumulative_gpa
                        )
                        st.session_state["gpa_input"] = (
                            latest_cumulative_gpa
                        )
                    st.session_state["pdf_detected_term_gpa"] = (
                        latest_term_gpa
                    )
                    passed_hours = sum(
                        int(advisor.courses.loc[cid, "Credits"])
                        for cid in set(extracted_passed)
                    )
                    failed_hours = sum(
                        int(advisor.courses.loc[cid, "Credits"])
                        for cid in set(extracted_failed)
                    )
                    st.session_state["pdf_detected_passed_hours"] = passed_hours
                    st.session_state["pdf_detected_failed_hours"] = failed_hours
                    st.session_state["pdf_extract_message"] = (
                        f"Extracted {len(attempt_records)} course attempts, "
                        f"including {sum(a['status'] == 'passed' for a in attempt_records)} "
                        "passed attempts, "
                        f"{sum(a['status'] == 'failed' for a in attempt_records)} "
                        "failed attempts, and "
                        f"{sum(a['status'] == 'unknown' for a in attempt_records)} "
                        "attempts with unknown status requiring review. "
                        f"Latest status: {len(extracted_passed)} passed courses "
                        f"and {len(extracted_failed)} failed courses. "
                        "Please select the academic year, last completed semester, "
                        "target semester, and specialization manually below."
                    )
                except Exception as exc:
                    st.error(f"Could not read the PDF file: {exc}")
        if st.session_state.get("pdf_extract_message"):
            st.info(st.session_state["pdf_extract_message"])
            unmatched_codes = st.session_state.get(
                "pdf_unmatched_codes",
                [],
            )
            if unmatched_codes:
                st.warning(
                    "Review these unmatched codes or unknown statuses: "
                    + ", ".join(unmatched_codes)
                )
            st.caption(
                "Review the extracted attempts before relying on the results. "
                "Scanned PDFs may require OCR or manual review."
            )
            attempts = st.session_state.get("pdf_attempt_records", [])
            if attempts:
                history_rows = []
                failure_counts = {}
                pass_counts = {}
                for attempt in attempts:
                    cid = attempt.get("course_id")
                    if cid:
                        if attempt["status"] == "failed":
                            failure_counts[cid] = (
                                failure_counts.get(cid, 0) + 1
                            )
                        elif attempt["status"] == "passed":
                            pass_counts[cid] = (
                                pass_counts.get(cid, 0) + 1
                            )
                    history_rows.append({
                        "Attempt Number": attempt["sequence"],
                        "Course Code": (
                            cid or attempt["course_code_normalized"]
                        ),
                        "Course Name": (
                            course_names.get(
                                cid,
                                "Not found in course catalog",
                            )
                            if cid
                            else "Not found in course catalog"
                        ),
                        "Status": {
                            "failed": "Failed",
                            "passed": "Passed",
                            "unknown": "Unknown - Review Transcript",
                        }.get(
                            attempt["status"],
                            "Unknown",
                        ),
                        "Page": attempt["page"],
                    })
                with st.expander(
                    "View All Course Attempts in Order",
                    expanded=True,
                ):
                    st.dataframe(
                        pd.DataFrame(history_rows),
                        use_container_width=True,
                        hide_index=True,
                    )
                summary_ids = sorted(
                    set(failure_counts) | set(pass_counts)
                )
                summary_rows = [{
                    "Course Code": cid,
                    "Course Name": course_names.get(cid, cid),
                    "Failed Attempts": failure_counts.get(cid, 0),
                    "Passed Attempts": pass_counts.get(cid, 0),
                    "Latest Status": (
                        "Passed"
                        if cid in st.session_state.get(
                            "pdf_detected_passed",
                            [],
                        )
                        else "Failed"
                    ),
                } for cid in summary_ids]
                with st.expander("Pass/Fail Attempt Counts by Course"):
                    st.dataframe(
                        pd.DataFrame(summary_rows),
                        use_container_width=True,
                        hide_index=True,
                    )
            if st.session_state.get("pdf_detected_gpa") is not None:
                term_gpa = st.session_state.get(
                    "pdf_detected_term_gpa"
                )
                gpa_text = (
                    "Extracted Cumulative GPA: "
                    f"{st.session_state['pdf_detected_gpa']:.3f}"
                )
                if term_gpa is not None:
                    gpa_text += f" - Latest Term GPA: {term_gpa:.3f}"
                st.info(gpa_text + ". Verify the extracted GPA.")
    else:
        st.info(
            "Manual entry selected. Enter the student's passed and failed courses below."
        )
        if (
            st.session_state.get("academic_record_entry_method_previous")
            != "Enter courses manually"
        ):
            st.session_state["passed_courses_input"] = []
            st.session_state["failed_courses_input"] = []
            st.session_state["gpa_input"] = 0.0
            for state_key in [
                key
                for key in list(st.session_state.keys())
                if key.startswith("pdf_")
            ]:
                del st.session_state[state_key]
    st.session_state[
        "academic_record_entry_method_previous"
    ] = entry_method
    # The student must manually choose these academic details.
    if "academic_year_input" not in st.session_state:
        st.session_state["academic_year_input"] = None
    if "last_completed_semester_input" not in st.session_state:
        st.session_state["last_completed_semester_input"] = None
    if "target_semester_input" not in st.session_state:
        st.session_state["target_semester_input"] = None
    year = st.selectbox(
        "1. Academic Year",
        [1, 2, 3, 4],
        index=(
            [1, 2, 3, 4].index(
                st.session_state["academic_year_input"]
            )
            if st.session_state["academic_year_input"] in [1, 2, 3, 4]
            else None
        ),
        placeholder="Choose academic year",
        format_func=lambda x: f"Year {x}",
        key="academic_year_input",
    )
    last_completed_semester = st.selectbox(
        "2. Last Completed Semester",
        semester_options,
        index=(
            semester_options.index(
                st.session_state["last_completed_semester_input"]
            )
            if st.session_state["last_completed_semester_input"]
            in semester_options
            else None
        ),
        placeholder="Choose last completed semester",
        format_func=lambda x: semester_names[x],
        key="last_completed_semester_input",
        help="The most recent semester the student has already completed.",
    )
    target_semester = st.selectbox(
        "3. Target Semester",
        semester_options,
        index=(
            semester_options.index(
                st.session_state["target_semester_input"]
            )
            if st.session_state["target_semester_input"]
            in semester_options
            else None
        ),
        placeholder="Choose target semester",
        format_func=lambda x: semester_names[x],
        key="target_semester_input",
        help="The semester for which course recommendations are generated.",
    )
    specialization = st.selectbox(
        "4. Department / Specialization",
        ["General", "IS", "CS", "AI"],
        index=0,
        key="specialization_input",
        help="Choose the student's department or specialization manually.",
    )
    first_semester = (
        year == 1
        and target_semester == 1
        and last_completed_semester is None
    )
    default_passed = [
        c
        for c in st.session_state.get("pdf_detected_passed", [])
        if c in all_course_ids
    ]
    default_failed = [
        c
        for c in st.session_state.get("pdf_detected_failed", [])
        if c in all_course_ids and c not in default_passed
    ]
    if first_semester:
        st.session_state["passed_courses_input"] = []
        st.session_state["failed_courses_input"] = []
        st.session_state["gpa_input"] = 0.0
        passed_courses = []
        failed_courses = []
        gpa = 0.0
        completed_credits = 0
        failed_credits = 0
        st.info(
            "New student selected. Previous courses, credit hours, and GPA "
            "are not required when no semester has been completed."
        )
    elif year is not None and target_semester is not None:
        if entry_method == "Enter courses manually":
            st.subheader("Manual Academic Record")
            passed_courses = st.multiselect(
                "5. Courses Passed",
                options=all_course_ids,
                format_func=lambda cid: course_names[cid],
                key="passed_courses_input",
                help="Select courses the student has passed.",
            )
            failed_options = [
                cid
                for cid in all_course_ids
                if cid not in passed_courses
            ]
            failed_courses = st.multiselect(
                "6. Courses Failed (if any)",
                options=failed_options,
                format_func=lambda cid: course_names[cid],
                key="failed_courses_input",
                help="Select courses whose latest attempt was failed.",
            )
            gpa = st.number_input(
                "7. Current Cumulative GPA",
                min_value=0.0,
                max_value=4.0,
                value=float(st.session_state.get("gpa_input", 0.0)),
                step=0.01,
                format="%.3f",
                key="gpa_input",
                help="Enter the student's current cumulative GPA.",
            )
        else:
            extracted_record_ready = (
                "pdf_attempt_records" in st.session_state
            )
            if extracted_record_ready:
                st.caption(
                    "Course history is populated from the uploaded statement. "
                    "Review the extraction summary above."
                )
            else:
                st.warning(
                    "Upload the transcript PDF and click "
                    "**Extract Courses from Transcript** before generating recommendations."
                )
            passed_courses = [
                c
                for c in st.session_state.get("pdf_detected_passed", [])
                if c in all_course_ids
            ]
            failed_courses = [
                c
                for c in st.session_state.get("pdf_detected_failed", [])
                if c in all_course_ids and c not in passed_courses
            ]
            extracted_gpa = st.session_state.get("pdf_detected_gpa")
            if extracted_gpa is not None:
                st.metric(
                    "Extracted Cumulative GPA",
                    f"{float(extracted_gpa):.3f}",
                )
                gpa = float(extracted_gpa)
            else:
                gpa = st.number_input(
                    "Current Cumulative GPA (not detected in PDF)",
                    min_value=0.0,
                    max_value=4.0,
                    value=float(st.session_state.get("gpa_input", 0.0)),
                    step=0.01,
                    format="%.3f",
                    key="gpa_input",
                )
        completed_credits = sum(
            int(advisor.courses.loc[cid, "Credits"])
            for cid in set(passed_courses)
        )
        failed_credits = sum(
            int(advisor.courses.loc[cid, "Credits"])
            for cid in set(failed_courses)
        )
        hours_cols = st.columns(2)
        hours_cols[0].metric(
            "Completed Credit Hours (Passed)",
            completed_credits,
        )
        hours_cols[1].metric(
            "Credit Hours Failed",
            failed_credits,
        )
        if entry_method == "Enter courses manually":
            st.subheader("Review Manual Entry")
            summary_cols = st.columns(4)
            summary_cols[0].metric(
                "Academic Year",
                f"Year {year}",
            )
            summary_cols[1].metric(
                "Last Completed Semester",
                semester_names.get(
                    last_completed_semester,
                    "Not selected",
                ),
            )
            summary_cols[2].metric(
                "Target Semester",
                semester_names.get(target_semester, "Not selected"),
            )
            summary_cols[3].metric(
                "Current GPA",
                f"{gpa:.3f}",
            )
            st.caption(
                f"Department / Specialization: {specialization}"
            )
            review_left, review_right = st.columns(2)
            with review_left:
                st.markdown("**Courses Passed**")
                if passed_courses:
                    st.dataframe(
                        pd.DataFrame([{
                            "Course Code": cid,
                            "Course Name (Arabic / English)": course_names[cid],
                            "Credits": int(
                                advisor.courses.loc[cid, "Credits"]
                            ),
                        } for cid in passed_courses]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("No passed courses selected.")
            with review_right:
                st.markdown("**Courses Failed**")
                if failed_courses:
                    st.dataframe(
                        pd.DataFrame([{
                            "Course Code": cid,
                            "Course Name (Arabic / English)": course_names[cid],
                            "Credits": int(
                                advisor.courses.loc[cid, "Credits"]
                            ),
                        } for cid in failed_courses]),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("No failed courses selected.")
    else:
        passed_courses = []
        failed_courses = []
        gpa = 0.0
        completed_credits = 0
        failed_credits = 0
        st.info(
            "Choose an academic year and target semester to continue. "
            "Choose the last completed semester when the student has previous study."
        )
    upload_record_ready = (
        entry_method == "Enter courses manually"
        or "pdf_attempt_records" in st.session_state
        or first_semester
    )
    can_generate = (
        year is not None
        and target_semester is not None
        and upload_record_ready
        and (
            first_semester
            or last_completed_semester is not None
        )
    )
    submitted = st.button(
        "Generate Recommendations",
        type="primary",
        use_container_width=True,
        disabled=not can_generate,
    )
    if submitted and can_generate:
        if not first_semester and gpa == 0.0:
            st.warning(
                "Enter the current GPA before relying on the recommendations."
            )
        if set(passed_courses) & set(failed_courses):
            st.error(
                "The same course cannot be selected as both passed and failed."
            )
        else:
            try:
                student = create_student_input(
                    student_id="STREAMLIT-TEST",
                    current_level=int(year),
                    completed_credits=int(completed_credits),
                    gpa=float(gpa),
                    specialization=specialization,
                    passed_courses=passed_courses,
                    failed_courses=failed_courses,
                )
                # Apply the credit-hour registration rules.
                if first_semester or float(gpa) >= 2.0:
                    minimum_required_credits = 12
                    maximum_allowed_credits = 18
                else:
                    minimum_required_credits = 12
                    # For GPA below 2.00, this implementation enforces
                    # the minimum of 12 hours without imposing an
                    # additional 18-hour maximum through this GPA rule.
                    maximum_allowed_credits = sum(
                        int(value)
                        for value in advisor.courses["Credits"]
                    )
                result = advisor.recommend(
                    student,
                    max_credits=maximum_allowed_credits,
                    min_credits=minimum_required_credits,
                    top_n=len(advisor.courses),
                    current_semester=int(target_semester),
                )
                result.setdefault("status", {})
                result.setdefault("student", {})
                result["status"]["failed_credits"] = int(failed_credits)
                result["status"]["total_passed_hours"] = int(completed_credits)
                result["status"]["total_failed_hours"] = int(failed_credits)
                result["status"]["minimum_credits_required"] = (
                    minimum_required_credits
                )
                result["status"]["maximum_credits_allowed"] = (
                    maximum_allowed_credits
                )
                result["status"]["failed_course_ids"] = list(failed_courses)
                if (
                    entry_method == "Upload transcript / statement"
                    and "pdf_attempt_records" in st.session_state
                ):
                    result["status"]["repeated_failure_advisories"] = (
                        get_repeated_failure_advisories(
                            st.session_state["pdf_attempt_records"]
                        )
                    )
                else:
                    result["status"]["repeated_failure_advisories"] = []
                result["student"]["last_completed_semester"] = (
                    semester_names.get(last_completed_semester)
                )
                result["student"]["target_semester"] = (
                    semester_names.get(target_semester)
                )
                result["student"]["department"] = specialization
                st.session_state["last_recommendation_result"] = result
            except Exception as exc:
                st.error(
                    "An error occurred while generating recommendations."
                )
                st.exception(exc)
    if "last_recommendation_result" in st.session_state:
        display_recommendations(
            st.session_state["last_recommendation_result"]
        )
    else:
        st.info(
            "Select the academic year, last completed semester, target semester, "
            "and department manually, then generate recommendations."
        )
# ---------------------------------------------------------------------
# GPA Calculator
# ---------------------------------------------------------------------
with tab_gpa:
    st.header("GPA Calculator")
    st.write(
        "Enter the numerical grade for each course to calculate the semester GPA."
    )
    st.caption(
        "Enter grades as numbers from 0 to 100. "
        "The grade-to-points mapping below is configurable and must match "
        "the official Fayoum University bylaws."
    )
    def percentage_to_grade_points(score: float) -> float:
        if score >= 90:
            return 4.0
        elif score >= 85:
            return 3.7
        elif score >= 80:
            return 3.3
        elif score >= 75:
            return 3.0
        elif score >= 70:
            return 2.7
        elif score >= 65:
            return 2.3
        elif score >= 60:
            return 2.0
        elif score >= 55:
            return 1.7
        elif score >= 50:
            return 1.0
        else:
            return 0.0
    previous_gpa = st.number_input(
        "Previous Cumulative GPA (optional)",
        min_value=0.0,
        max_value=4.0,
        value=0.0,
        step=0.01,
        format="%.3f",
        key="gpa_calculator_previous_gpa",
    )
    previous_hours = st.number_input(
        "Previously Completed Credit Hours",
        min_value=0,
        max_value=300,
        value=0,
        step=1,
        key="gpa_calculator_previous_hours",
    )
    selected_gpa_courses = st.multiselect(
        "Select Courses Taken This Semester",
        options=all_course_ids,
        format_func=lambda cid: course_names[cid],
        key="gpa_calculator_courses",
    )
    semester_quality_points = 0.0
    semester_credit_hours = 0
    semester_weighted_percentage = 0.0
    gpa_course_rows = []
    if selected_gpa_courses:
        st.subheader("Enter Numerical Grades")
        for cid in selected_gpa_courses:
            credits = int(advisor.courses.loc[cid, "Credits"])
            score = st.number_input(
                f"{cid} — {bilingual_course_name(cid)} ({credits} credits)",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=1.0,
                format="%.1f",
                key=f"gpa_calculator_score_{cid}",
                help="Enter the student's final course percentage from 0 to 100.",
            )
            grade_points = percentage_to_grade_points(score)
            semester_quality_points += credits * grade_points
            semester_weighted_percentage += credits * score
            semester_credit_hours += credits
            gpa_course_rows.append({
                "Course Code": cid,
                "Course Name": bilingual_course_name(cid),
                "Credits": credits,
                "Numerical Grade": score,
                "GPA Points": grade_points,
                "Quality Points": credits * grade_points,
            })
        st.dataframe(
            pd.DataFrame(gpa_course_rows),
            use_container_width=True,
            hide_index=True,
        )
        if semester_credit_hours > 0:
            semester_gpa = (
                semester_quality_points / semester_credit_hours
            )
            semester_average = (
                semester_weighted_percentage / semester_credit_hours
            )
            st.subheader("Semester GPA Result")
            result_cols = st.columns(4)
            result_cols[0].metric(
                "Semester GPA (4.0 Scale)",
                f"{semester_gpa:.3f}",
            )
            result_cols[1].metric(
                "Semester Average (%)",
                f"{semester_average:.2f}%",
            )
            result_cols[2].metric(
                "Semester Credit Hours",
                semester_credit_hours,
            )
            result_cols[3].metric(
                "Total Quality Points",
                f"{semester_quality_points:.2f}",
            )
            st.caption(
                "The semester GPA and percentage average are weighted by "
                "the credit hours of each course."
            )
            if st.button(
                "Calculate Cumulative GPA",
                use_container_width=True,
                key="calculate_cumulative_gpa_button",
            ):
                total_hours = previous_hours + semester_credit_hours
                if previous_hours > 0:
                    cumulative_gpa = (
                        previous_gpa * previous_hours
                        + semester_quality_points
                    ) / total_hours
                else:
                    cumulative_gpa = semester_gpa
                st.subheader("Cumulative GPA Result")
                cumulative_cols = st.columns(2)
                cumulative_cols[0].metric(
                    "Estimated Cumulative GPA",
                    f"{cumulative_gpa:.3f}",
                )
                cumulative_cols[1].metric(
                    "Total Credit Hours",
                    total_hours,
                )
                st.caption(
                    "This estimate assumes the previous GPA and all selected "
                    "course grades are weighted by credit hours. Official "
                    "repeat-course and exclusion rules may change the result."
                )
    else:
        st.info(
            "Select at least one course to enter numerical grades."
        )
# ---------------------------------------------------------------------
# Course Catalog
# ---------------------------------------------------------------------
with tab_catalog:
    st.header("Course Catalog")
    search_term = st.text_input(
        "Search by course code or name",
        placeholder="Example: Data Structures or CS211",
    )
    all_courses = advisor.get_all_courses()
    if search_term.strip():
        term = search_term.strip().lower()
        filtered = [
            course
            for course in all_courses
            if term in str(
                course.get("course_id", course.get("Course_ID", ""))
            ).casefold()
            or term in str(
                course.get(
                    "course_name",
                    course.get(
                        "Course_Name",
                        course.get("name_en", course.get("name", "")),
                    ),
                )
            ).casefold()
            or term in str(
                course.get(
                    "course_name_ar",
                    course.get(
                        "Course_Name_Arabic",
                        course.get("name_ar", course.get("arabic_name", "")),
                    ),
                )
            ).casefold()
            or term in str(
                course.get("course_name_display", "")
            ).casefold()
            or term in str(course.get("name", "")).casefold()
        ]
    else:
        filtered = all_courses
    if filtered:
        catalog_rows = []
        for course in filtered:
            catalog_rows.append({
                "Course Code": course.get(
                    "course_id",
                    course.get("Course_ID", ""),
                ),
                "Course Name (Arabic / English)": (
                    course.get("course_name_display")
                    or " / ".join(
                        part
                        for part in [
                            _clean_course_name(
                                course.get(
                                    "course_name_ar",
                                    course.get(
                                        "Course_Name_Arabic",
                                        course.get(
                                            "name_ar",
                                            course.get("arabic_name", ""),
                                        ),
                                    ),
                                )
                            ),
                            _clean_course_name(
                                course.get(
                                    "course_name",
                                    course.get(
                                        "Course_Name",
                                        course.get(
                                            "name_en",
                                            course.get("name", ""),
                                        ),
                                    ),
                                )
                            ),
                        ]
                        if part
                    )
                ),
                "Credits": course.get(
                    "credits",
                    course.get("Credits", ""),
                ),
                "Type": course.get(
                    "type",
                    course.get("Type", ""),
                ),
                "Category": course.get(
                    "category",
                    course.get("Category", ""),
                ),
            })
        st.dataframe(
            pd.DataFrame(catalog_rows),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Courses displayed: {len(catalog_rows)}")
    else:
        st.warning("No courses match your search.")
    with st.expander("View Course Details"):
        selected_course = st.selectbox(
            "Course",
            all_course_ids,
            format_func=lambda cid: course_names[cid],
            key="course_detail",
        )
        details = advisor.get_course_info(selected_course)
        st.json(
            details
            if details is not None
            else {"message": "Course not found"}
        )
# ---------------------------------------------------------------------
# Academic Rules
# ---------------------------------------------------------------------
with tab_rules:
    st.header("Academic Rules and System Settings")
    st.json({
        "institution": advisor.rules.get(
            "institution",
            "Fayoum University",
        ),
        "faculty": advisor.rules.get(
            "faculty",
            "Faculty of Computers and Information",
        ),
        "bylaws_year": advisor.rules.get("year", 2019),
        "total_credits_required": advisor.rules.get(
            "total_credits_required",
            144,
        ),
        "minimum_gpa_for_graduation": advisor.rules.get(
            "min_gpa_for_graduation",
            2.0,
        ),
        "semester_limits": advisor.rules.get(
            "semester_limits",
            {},
        ),
        "grade_points": advisor.grade_points,
        "overall_grade": advisor.rules.get(
            "overall_grade",
            {},
        ),
        "level_names": advisor.rules.get(
            "level_names",
            {},
        ),
    })
st.divider()
st.caption(
    "This is a test version. Verify recommendations against the official "
    "academic regulations before relying on them."
)