---
### تجربة المشروع باستخدام Streamlit

لو عايز تشغّل المشروع وتشوف بيشتغل إزاي، نزّل الـ Repository على جهازك من الرابط ده:

https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation

بعد ما تنزّله، افتح الـ Terminal داخل فولدر المشروع، وشغّل الأمر ده:

```bash
python -m streamlit run streamlit_app.py
```

بعدها افتح الرابط ده في المتصفح:

http://localhost:8501

وهتقدر تجرب المشروع وتشوف طريقة عمله بنفسك.


---
# Edu Advisor — FastAPI Backend

**Academic Course Recommendation System**  
Fayoum University — Faculty of Computers and Information

Edu Advisor is a rule-based academic course recommendation system designed to help students identify suitable courses for their upcoming semester based on their academic records, prerequisites, GPA, academic level, and university regulations.

This FastAPI implementation exposes the project's core functionality through REST API endpoints, allowing web and mobile applications to integrate with the recommendation engine.

## 1. Project Overview

The backend provides the following capabilities:

- **Course Recommendations:** Generate ranked recommendations based on academic eligibility, prerequisites, course priorities, and credit-hour limits.
- **Academic Record Management:** Accept manually entered student information or extracted transcript data.
- **PDF Transcript Extraction:** Extract course attempts, pass/fail statuses, and estimated GPA values from text-based PDF transcripts.
- **Repeated Failure Advisories:** Identify courses with multiple failed attempts when the latest recorded attempt is failed.
- **GPA Calculator:** Calculate semester GPA and estimate cumulative GPA.
- **Course Catalog:** Retrieve, search, and filter academic courses.
- **Academic Rules:** Access the university regulations stored in JSON files.
- **PDF Report Export:** Generate downloadable course recommendation reports.

**Important:** Edu Advisor is an academic decision-support tool. Its recommendations must be verified against the official university bylaws before course registration.

## 2. Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Backend Framework | FastAPI |
| API Documentation | Swagger UI / OpenAPI |
| ASGI Server | Uvicorn |
| Recommendation Engine | Rule-Based Python Engine |
| Data Storage | JSON Files |
| Data Processing | Pandas |
| PDF Extraction | pypdf |
| PDF Report Generation | ReportLab |

The implementation does not require a trained machine learning model.

## 3. System Architecture

```text
             Web / Mobile Application
                       |
                  HTTP Request
                       |
                       v
                FastAPI (main.py)
                       |
             +---------+---------+
             |                   |
             v                   v
        services.py        recommender.py
             |                   |
     PDF Extraction         Eligibility Rules
     GPA Calculation        Prerequisite Checks
     PDF Reports            Course Ranking
                                 |
                                 v
                          data/*.json
             |                   |
             +---------+---------+
                       |
                       v
              JSON / PDF Response
```

The backend is responsible for processing requests and returning results. The frontend is responsible for displaying forms, tables, warnings, and downloadable files.

## 4. Project Structure

```text
Edu-Advisor/
├── main.py
├── recommender.py
├── services.py
├── streamlit_app.py          # If retained in the repository
├── requirements.txt
├── README.md
├── data/
│   ├── bylaws_courses.json
│   ├── bylaws_prerequisites.json
│   └── bylaws_rules.json
└── explain/
    └── docs/
        └── functions/
```

### Main Files

**`main.py`**  
Defines the REST API endpoints, validates incoming requests, and prepares API responses.

**`recommender.py`**  
Contains the `EduAdvisor` recommendation engine, including course eligibility, prerequisite validation, ranking, and recommendation generation.

**`services.py`**  
Contains supporting functionality for PDF transcript processing, GPA calculations, academic advisories, and report generation.

**`streamlit_app.py`**  
The original Streamlit interface, where retained. It can be used to understand the earlier interactive workflows.

**`data/`**  
Contains course catalog information, prerequisite relationships, and academic rules.

## 5. Installation and Setup

### Requirements

- Python 3.10 or later is recommended.
- pip
- Git (optional)
- A Python virtual environment is recommended.

### Step 1 — Open the Project

```bash
cd Edu-Advisor
```

### Step 2 — Create a Virtual Environment

```bash
python -m venv .venv
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On Linux or macOS:

```bash
source .venv/bin/activate
```

### Step 3 — Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### Step 4 — Start the Backend

```bash
python -m uvicorn main:app --reload
```

### Step 5 — Open API Documentation

After starting the server, visit:

- **Swagger UI:** http://127.0.0.1:8000/docs
- **OpenAPI Schema:** http://127.0.0.1:8000/openapi.json
- **Health Check:** http://127.0.0.1:8000/api/v1/health

The `--reload` option is intended for local development, not production deployment.

## 6. API Endpoints — Version 1

The following endpoints are documented under the `/api/v1` prefix.

### General and Academic Data

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/health` | Check API health |
| GET | `/api/v1/config/options` | Retrieve academic years, semesters, and specializations |
| GET | `/api/v1/courses` | Retrieve, filter, and search courses |
| GET | `/api/v1/courses/{course_id}` | Retrieve course information and prerequisites |
| GET | `/api/v1/academic-rules` | Retrieve academic regulations |
| GET | `/api/v1/prerequisites` | Retrieve prerequisite relationships |

### Transcript Processing

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/transcripts/extract` | Extract academic data from an uploaded PDF |
| POST | `/api/v1/transcripts/attempts` | Process extracted course attempts |
| POST | `/api/v1/transcripts/summary` | Generate an academic attempt summary |

### Recommendations

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/recommendations` | Generate course recommendations |
| POST | `/api/v1/recommendations/advisories` | Generate academic advisories |
| POST | `/api/v1/students/academic-summary` | Generate a student academic summary |
| POST | `/api/v1/registration/limits` | Retrieve registration credit-hour limits |
| POST | `/api/v1/recommendations/export` | Export recommendations as PDF |

### GPA Calculation

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/gpa/semester` | Calculate semester GPA |
| POST | `/api/v1/gpa/cumulative` | Estimate cumulative GPA |

**Total: 16 documented versioned endpoints.**

## 7. Legacy API Endpoints

The project documentation also describes the following older routes under `/api`.

| Method | Endpoint |
|---|---|
| GET | `/api/health` |
| GET | `/api/options` |
| GET | `/api/courses` |
| GET | `/api/courses/{course_id}` |
| GET | `/api/academic-rules` |
| POST | `/api/transcripts/extract` |
| POST | `/api/recommendations` |
| POST | `/api/gpa/calculate` |
| POST | `/api/recommendations/export-pdf` |

These routes are documented for backward compatibility. Developers should verify which routes are enabled in the current `main.py` and prefer `/api/v1` for new integrations.

## 8. Course Recommendation Workflow

### Manual Entry

1. Retrieve academic options from `/api/v1/config/options`.
2. Retrieve available catalog courses from `/api/v1/courses`.
3. Collect the student's academic year, last completed semester, target semester, specialization, and GPA.
4. Collect passed and failed course codes.
5. Submit the academic record to `/api/v1/recommendations`.
6. Display the returned recommendations, academic status, and warnings.

### Example Recommendation Request

```json
{
  "student_id": "S001",
  "academic_year": 2,
  "last_completed_semester": 1,
  "target_semester": 2,
  "specialization": "IS",
  "gpa": 2.8,
  "passed_courses": ["BS101", "CS101"],
  "failed_courses": [],
  "attempts": []
}
```

### Academic Input Fields

| Field | Description |
|---|---|
| `student_id` | Student identifier |
| `academic_year` | Academic year from 1 to 4 |
| `last_completed_semester` | Most recently completed semester |
| `target_semester` | Semester for which recommendations are requested |
| `specialization` | Department or specialization |
| `gpa` | Current cumulative GPA |
| `passed_courses` | Courses successfully completed |
| `failed_courses` | Courses whose latest known attempt was failed |
| `attempts` | Optional course attempt history |

Semester values:

- `1` — Fall
- `2` — Spring
- `3` — Summer

For a new first-year student with no completed semester, `last_completed_semester` can be `null`, with no previous courses or cumulative GPA.

The example field names must be checked against the live OpenAPI schema before frontend integration.

## 9. Recommendation Engine

The recommendation engine is implemented in `recommender.py` using academic rules rather than machine learning.

### Recommendation Process

**Step 1 — Load Academic Data**

Load course information, prerequisites, and academic rules from the JSON datasets.

**Step 2 — Check Eligibility**

Evaluate whether each course can be recommended based on passed courses, prerequisites, academic level, and other implemented conditions.

**Step 3 — Check Semester Availability**

Determine whether the course is considered available in the selected semester.

**Step 4 — Calculate Priority**

Calculate a recommendation score using factors such as retakes, course type, academic level, GPA, and the courses unlocked by completing a prerequisite.

**Step 5 — Rank Courses**

Prioritize retake courses and sort other eligible courses using the implemented ranking rules.

**Step 6 — Return Recommendations**

Return the recommended courses along with academic status information and reasons for each recommendation.

**Important:** The current availability rules are based on assumptions in the recommendation engine, not a verified offered-courses-per-semester dataset.

## 10. PDF Transcript Extraction

The transcript extraction workflow accepts text-based PDF academic records.

### Workflow

1. Upload the PDF to `/api/v1/transcripts/extract`.
2. Extract course codes and attempt statuses.
3. Identify passed and failed courses based on their latest recorded attempts.
4. Attempt to extract cumulative and semester GPA values.
5. Review the extracted information.
6. Submit the confirmed academic record to `/api/v1/recommendations`.

### Current Extraction Rules

The documented extraction process recognizes:

- `X` — Failed
- `Y` or `¥` — Passed

It also attempts to identify GPA values from decimal numbers appearing in the transcript.

### Limitations

- Scanned or image-only PDFs require OCR, which is not implemented in the documented backend.
- GPA extraction is heuristic and may select an incorrect value.
- Unknown course codes or statuses require manual review.
- Repeated attempts must be interpreted in their recorded order.

The frontend should always provide a review step before relying on extracted academic records.

## 11. Repeated Failure Advisories

The system can identify courses failed multiple times.

An advisory is generated when:

- A course has at least two recorded failed attempts.
- The latest recorded attempt is failed.

For example:

```text
CS211 -> Failed
CS211 -> Failed
```

This may generate an advisory.

However:

```text
CS211 -> Failed
CS211 -> Failed
CS211 -> Passed
```

This should not generate the same advisory because the latest attempt is passed.

Academic advisories are informational and do not automatically prevent course registration.

## 12. GPA Calculator

The API supports semester GPA calculation and estimated cumulative GPA calculation.

### Example GPA Request

```json
{
  "previous_gpa": 2.8,
  "previous_hours": 30,
  "grades": [
    {
      "course_id": "BS101",
      "score": 88
    },
    {
      "course_id": "CS101",
      "score": 75
    }
  ]
}
```

### Semester GPA Formula

\[
\text{Semester GPA} =
\frac{\sum(\text{Credit Hours} \times \text{Grade Points})}
{\sum \text{Credit Hours}}
\]

### Estimated Cumulative GPA Formula

\[
\text{Cumulative GPA} =
\frac{(\text{Previous GPA} \times \text{Previous Hours}) + \text{Semester Quality Points}}
{\text{Previous Hours} + \text{Semester Hours}}
\]

The percentage-to-grade-point conversion follows the documented Streamlit implementation and must be reviewed against the official academic bylaws.

The estimated cumulative GPA may differ from the official GPA when repeat-course or grade-exclusion rules apply.

## 13. Academic Rules and Credit Hours

The supplied academic rules documentation includes:

| Rule | Documented Value |
|---|---|
| Graduation credit hours | 144 |
| Minimum graduation GPA | 2.0 |
| Normal semester minimum | 12 hours |
| Normal semester maximum | 18 hours |
| Summer minimum | 6 hours |
| Summer maximum | 12 hours |

These values are reference data, not a guarantee that every rule is fully enforced by the current implementation.

In particular, the documented behavior for GPA below 2.0 preserves a 12-credit minimum without applying the usual 18-credit maximum through that GPA rule.

This behavior requires academic verification before production use.

## 14. PDF Recommendation Report

The backend provides PDF report generation through:

`POST /api/v1/recommendations/export`

The report can include:

- Student academic information
- Current GPA
- Passed and failed credit hours
- Recommended courses
- Course codes and names
- Credit hours
- Recommendation reasons
- Retake indicators

**Known limitation:** Arabic text may not render correctly with ReportLab's standard fonts. Proper Arabic Unicode fonts and right-to-left text shaping may be required.

## 15. API and Frontend Responsibilities

| FastAPI Backend | Web / Mobile Frontend |
|---|---|
| Validate request data | Display input forms |
| Process transcript PDFs | Upload files and display extracted results |
| Calculate recommendations | Show recommendation tables |
| Calculate GPA | Display GPA results |
| Return academic warnings | Present warnings to students |
| Generate PDF files | Provide download controls |
| Return JSON responses | Manage interface state |

The documented backend does not persist individual student records in a database or maintain the original Streamlit session state between requests.

The frontend must retain relevant user information and send it again when required.

## 16. Known Limitations and Future Improvements

The following areas require further work or verification:

1. **Real Course Availability:** Integrate an official offered-courses-per-semester dataset.
2. **Academic Rules Validation:** Verify registration, retake, warning, and graduation rules against approved bylaws.
3. **Specialization Consistency:** Review differences between available specialization options and the official department list.
4. **OCR Support:** Add scanned transcript processing when required.
5. **GPA Extraction Accuracy:** Improve transcript-specific GPA parsing.
6. **Arabic PDF Support:** Implement appropriate Arabic fonts and text shaping.
7. **Authentication and Privacy:** Protect student records before exposing the API publicly.
8. **Data Persistence:** Add a database only when the application requires persistent student accounts or records.
9. **Automated Testing:** Add tests for academic eligibility, prerequisites, retakes, GPA, and PDF extraction.
10. **Deployment:** Configure a secure production environment with HTTPS, request limits, and error monitoring.

## 17. Testing Checklist

Before handing over or deploying the backend, verify:

- [ ] The FastAPI application starts successfully.
- [ ] Swagger UI loads at `/docs`.
- [ ] The health-check endpoint returns successfully.
- [ ] The course catalog loads correctly.
- [ ] Invalid course IDs are handled properly.
- [ ] First-year students can generate recommendations.
- [ ] Passed courses are excluded from recommendations.
- [ ] Missing prerequisites prevent inappropriate new-course recommendations.
- [ ] Eligible failed courses are handled as retakes.
- [ ] Course ranking and credit-hour calculations are correct.
- [ ] Repeated failures generate the appropriate advisory.
- [ ] A later passing attempt removes the repeated-failure advisory.
- [ ] GPA results match manually calculated examples.
- [ ] Invalid or unreadable PDFs are handled appropriately.
- [ ] Recommendation reports are generated successfully.
- [ ] Arabic and English course names are displayed correctly.

This checklist identifies required tests; it does not imply that all tests have already passed.

## 18. Documentation and Repository

**GitHub Repository:**  
https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation

**Main Branch:** `master`

**Function Documentation:**  
https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/tree/master/explain/docs/functions

The function documentation is intended to help future developers understand the responsibilities and internal behavior of the project.

For changes to the recommendation logic, review the relevant function documentation before modifying the code.

## 19. Handover Notes

For developers continuing this project:

1. Start by understanding the JSON datasets and academic rules.
2. Review `recommender.py` before modifying recommendation behavior.
3. Review `services.py` for PDF, GPA, and report-related functionality.
4. Use `main.py` and `/docs` to understand the available API contracts.
5. Test existing scenarios before and after every modification.
6. Confirm academic rules with the appropriate university authority.
7. Document all changes for future maintainers.

Avoid changing unrelated functions when implementing a specific feature.

## 20. Final Note from the Developer


في النهاية، حابب أقول إني حاولت قدر الإمكان أقدم أفضل حاجة أقدر عليها في المشروع ده، سواء في كتابة الكود أو تنظيمه أو توثيقه، عشان أسهّل المهمة على أي حد هيكمل الشغل بعدي.

أكيد المشروع مش كامل، وممكن تكون فيه حاجات محتاجة تحسين، أو أجزاء صعبة في الفهم، أو حتى أخطاء غير مقصودة. لكن أحب أوضح إن كل ده مش عن إهمال، وإنما نتيجة حدود الوقت والخبرة والإمكانيات المتاحة ليا وقت التنفيذ.

أتمنى إن المجهود اللي اتبذل يكون نقطة بداية كويسة للي هيكمل المشروع، وإنه يقدر يطوّره ويخليه أفضل بكتير.

**وفي النهاية، إن أصبت فمن الله، وإن أخطأت فمن نفسي.**


---

**Project:** Edu Advisor  
**Institution:** Fayoum University — Faculty of Computers and Information  
**Documentation Updated:** October 26, 2026  
**Status:** Development / Academic Validation Required
