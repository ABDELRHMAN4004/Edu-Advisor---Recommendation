"""FastAPI replacement for the supplied Edu Advisor Streamlit UI.

All input/output workflows are JSON endpoints. The browser widgets themselves
are not part of FastAPI; connect a frontend to these routes or use /docs.
"""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from recommender import EduAdvisor, create_student_input
from services import SEMESTERS, calculate_gpa, course_display, extract_transcript, recommendations_pdf, repeated_failure_advisories

BASE = Path(__file__).resolve().parent
advisor = EduAdvisor(data_dir=BASE / 'data')
app = FastAPI(title='Edu Advisor API', version='1.0.0', description='FastAPI conversion of the Streamlit course recommendations, transcript extraction, GPA calculator, catalog and academic rules.')
app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000','http://localhost:5173','http://127.0.0.1:3000','http://127.0.0.1:5173'], allow_methods=['*'], allow_headers=['*'])

class RecommendationRequest(BaseModel):
    student_id: str = 'API-STUDENT'
    academic_year: int = Field(ge=1, le=4)
    last_completed_semester: Optional[int] = Field(default=None, ge=1, le=3)
    target_semester: int = Field(ge=1, le=3)
    specialization: str = 'General'
    gpa: float = Field(default=0.0, ge=0, le=4)
    passed_courses: list[str] = Field(default_factory=list)
    failed_courses: list[str] = Field(default_factory=list)
    attempt_records: list[dict] = Field(default_factory=list, description='Optional records returned by /api/transcripts/extract; enables repeated-failure advisories.')
    @model_validator(mode='after')
    def validate_record(self):
        if self.specialization not in {'General','IS','CS','AI'}:
            raise ValueError('specialization must be General, IS, CS, or AI')
        if self.academic_year == 1 and self.target_semester == 1 and self.last_completed_semester is None:
            if self.passed_courses or self.failed_courses:
                raise ValueError('New first-semester students must not have previous course records')
        elif self.last_completed_semester is None:
            raise ValueError('last_completed_semester is required except for a new first-semester student')
        if set(self.passed_courses) & set(self.failed_courses):
            raise ValueError('A course cannot be both passed and failed')
        unknown = (set(self.passed_courses) | set(self.failed_courses)) - advisor.all_courses
        if unknown:
            raise ValueError('Unknown course codes: ' + ', '.join(sorted(unknown)))
        return self

class GPAItem(BaseModel):
    course_id: str
    score: float = Field(ge=0, le=100)

class GPARequest(BaseModel):
    grades: list[GPAItem] = Field(min_length=1)
    previous_gpa: float = Field(default=0.0, ge=0, le=4)
    previous_hours: int = Field(default=0, ge=0, le=300)

class ExportRequest(BaseModel):
    result: dict

@app.get('/')
def root():
    return {'name':'Edu Advisor API','docs':'/docs','features':['recommendations','transcript PDF extraction','repeated failures','GPA calculator','course catalog','academic rules','PDF export']}

@app.get('/api/health')
def health():
    return {'status':'healthy','total_courses':len(advisor.all_courses)}

@app.get('/api/options')
def options():
    return {'academic_years':[1,2,3,4],'semesters':SEMESTERS,'specializations':['General','IS','CS','AI'],'new_student':{'academic_year':1,'target_semester':1,'last_completed_semester':None},'entry_methods':['manual','transcript_pdf']}

@app.get('/api/courses')
def courses(search: str = '', level: Optional[int] = None, category: Optional[str] = None, limit: Optional[int] = None):
    items = advisor.get_all_courses()
    if search.strip():
        term = search.strip().casefold()
        items = [c for c in items if term in str(c.get('course_id','')).casefold() or term in str(c.get('course_name','')).casefold() or term in str(c.get('course_name_ar','')).casefold() or term in str(c.get('course_name_display','')).casefold()]
    if level is not None: items = [c for c in items if c['level'] == level]
    if category is not None: items = [c for c in items if c['category'] == category]
    total = len(items)
    return {'total':total,'courses':items[:max(limit,0)] if limit is not None else items}

@app.get('/api/courses/{course_id}')
def course_info(course_id: str):
    info = advisor.get_course_info(course_id)
    if info is None: raise HTTPException(404,'Course not found')
    return info

@app.get('/api/academic-rules')
def academic_rules():
    return advisor.rules

@app.post('/api/transcripts/extract')
async def transcript_extract(file: UploadFile = File(...)):
    if not (file.filename or '').lower().endswith('.pdf'):
        raise HTTPException(400,'Upload a PDF file')
    data = await file.read(10*1024*1024 + 1)
    if len(data) > 10*1024*1024: raise HTTPException(413,'PDF exceeds 10 MB')
    if not data.startswith(b'%PDF'): raise HTTPException(400,'Invalid PDF header')
    try: return extract_transcript(data,advisor)
    except Exception as exc: raise HTTPException(422,f'Cannot extract PDF: {exc}') from exc

@app.post('/api/recommendations')
def recommend(request: RecommendationRequest):
    first_semester = request.academic_year == 1 and request.target_semester == 1 and request.last_completed_semester is None
    passed = [] if first_semester else request.passed_courses
    failed = [] if first_semester else request.failed_courses
    gpa = 0.0 if first_semester else request.gpa
    passed_hours = sum(int(advisor.courses.loc[c,'Credits']) for c in set(passed))
    failed_hours = sum(int(advisor.courses.loc[c,'Credits']) for c in set(failed))
    student = create_student_input(student_id=request.student_id,current_level=request.academic_year,completed_credits=passed_hours,gpa=gpa,specialization=request.specialization,passed_courses=passed,failed_courses=failed)
    min_credits = 12
    max_credits = 18 if first_semester or gpa >= 2.0 else sum(int(v) for v in advisor.courses['Credits'])
    try:
        result = advisor.recommend(student,max_credits=max_credits,min_credits=min_credits,top_n=len(advisor.courses),current_semester=request.target_semester)
    except ValueError as exc: raise HTTPException(400,str(exc)) from exc
    result.setdefault('status',{}).update({'failed_credits':failed_hours,'total_passed_hours':passed_hours,'total_failed_hours':failed_hours,'minimum_credits_required':min_credits,'maximum_credits_allowed':max_credits,'failed_course_ids':failed})
    from services import repeated_failure_advisories
    result['status']['repeated_failure_advisories'] = repeated_failure_advisories(request.attempt_records,advisor) if request.attempt_records else []
    result['student'].update({'last_completed_semester':SEMESTERS.get(request.last_completed_semester),'target_semester':SEMESTERS[request.target_semester],'department':request.specialization,'academic_year':request.academic_year})
    for rec in result.get('recommendations',[]):
        rec['course_name_display'] = course_display(advisor,rec['course_id'])
    result['total_recommended_credits'] = sum(int(r['credits']) for r in result.get('recommendations',[]))
    result['registration_warnings'] = []
    if result['total_recommended_credits'] < min_credits: result['registration_warnings'].append(f'Recommendations are below the minimum {min_credits} credit hours')
    if result['total_recommended_credits'] > max_credits: result['registration_warnings'].append(f'Recommendations exceed the maximum {max_credits} credit hours')
    return result

@app.post('/api/gpa/calculate')
def gpa_calculate(request: GPARequest):
    codes = [g.course_id for g in request.grades]
    unknown = sorted(set(codes) - advisor.all_courses)
    if unknown: raise HTTPException(400,{'unknown_courses':unknown})
    if len(set(codes)) != len(codes): raise HTTPException(400,'Duplicate course codes are not allowed')
    return calculate_gpa(advisor,[g.model_dump() for g in request.grades],request.previous_gpa,request.previous_hours)

@app.post('/api/recommendations/export-pdf')
def export_pdf(request: ExportRequest):
    try: content = recommendations_pdf(request.result)
    except Exception as exc: raise HTTPException(422,f'Could not generate PDF: {exc}') from exc
    return Response(content,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="edu_advisor_recommendations.pdf"'})


# Versioned endpoints. Existing /api routes remain available for compatibility.
class TranscriptDataRequest(BaseModel):
    attempts: list[dict] = Field(default_factory=list)
    passed_courses: list[str] = Field(default_factory=list)
    failed_courses: list[str] = Field(default_factory=list)
    cumulative_gpa: Optional[float] = None
    latest_term_gpa: Optional[float] = None

class AttemptsRequest(BaseModel):
    attempts: list[dict] = Field(default_factory=list)

class AdvisoryRequest(BaseModel):
    attempts: list[dict] = Field(default_factory=list)

class StudentSummaryRequest(BaseModel):
    academic_year: int = Field(ge=1, le=4)
    last_completed_semester: Optional[int] = Field(default=None, ge=1, le=3)
    target_semester: int = Field(ge=1, le=3)
    specialization: str = 'General'
    gpa: float = Field(ge=0, le=4)
    passed_courses: list[str] = Field(default_factory=list)
    failed_courses: list[str] = Field(default_factory=list)

class RegistrationRequest(BaseModel):
    gpa: float = Field(ge=0, le=4)
    academic_year: int = Field(ge=1, le=4)
    target_semester: int = Field(ge=1, le=3)
    last_completed_semester: Optional[int] = Field(default=None, ge=1, le=3)

class SemesterGPARequest(BaseModel):
    grades: list[GPAItem] = Field(min_length=1)

class CumulativeGPARequest(GPARequest):
    pass

def _check_course_codes(passed: list[str], failed: list[str]):
    unknown = (set(passed) | set(failed)) - advisor.all_courses
    if unknown:
        raise HTTPException(400, {'unknown_courses': sorted(unknown)})
    if set(passed) & set(failed):
        raise HTTPException(400, 'The same course cannot be passed and failed')

def _gpa_data(grades: list[GPAItem], previous_gpa: float = 0.0, previous_hours: int = 0):
    codes = [g.course_id for g in grades]
    _check_course_codes(codes, [])
    if len(codes) != len(set(codes)):
        raise HTTPException(400, 'Duplicate course codes are not allowed')
    return calculate_gpa(advisor, [g.model_dump() for g in grades], previous_gpa, previous_hours)

@app.get('/api/v1/health', tags=['Health'])
def v1_health():
    return health()

@app.get('/api/v1/config/options', tags=['Config'])
def v1_options():
    return options()

@app.get('/api/v1/courses', tags=['Courses'])
def v1_courses(search: str = '', level: Optional[int] = None, category: Optional[str] = None, limit: Optional[int] = None):
    return courses(search, level, category, limit)

@app.get('/api/v1/courses/{course_id}', tags=['Courses'])
def v1_course(course_id: str):
    return course_info(course_id)

@app.get('/api/v1/academic-rules', tags=['Academic Rules'])
def v1_rules():
    return academic_rules()

@app.get('/api/v1/prerequisites', tags=['Prerequisites'])
def v1_prerequisites(course_id: Optional[str] = None):
    if course_id:
        if course_id not in advisor.all_courses:
            raise HTTPException(404, 'Course not found')
        return {'course_id': course_id, 'prerequisites': advisor.prereq_map.get(course_id, [])}
    return advisor.prereq_map

@app.post('/api/v1/transcripts/extract', tags=['Transcript Extract'])
async def v1_transcript_extract(file: UploadFile = File(...)):
    return await transcript_extract(file)

@app.post('/api/v1/transcripts/summary', tags=['Transcript Summary'])
def v1_transcript_summary(request: TranscriptDataRequest):
    _check_course_codes(request.passed_courses, request.failed_courses)
    passed_hours = sum(int(advisor.courses.loc[c, 'Credits']) for c in set(request.passed_courses))
    failed_hours = sum(int(advisor.courses.loc[c, 'Credits']) for c in set(request.failed_courses))
    return {'passed_courses': request.passed_courses, 'failed_courses': request.failed_courses,
            'passed_courses_count': len(set(request.passed_courses)), 'failed_courses_count': len(set(request.failed_courses)),
            'passed_hours': passed_hours, 'failed_hours': failed_hours,
            'cumulative_gpa': request.cumulative_gpa, 'latest_term_gpa': request.latest_term_gpa,
            'attempts_count': len(request.attempts),
            'repeated_failure_advisories': repeated_failure_advisories(request.attempts, advisor)}

@app.post('/api/v1/transcripts/attempts', tags=['Transcript Attempts'])
def v1_transcript_attempts(request: AttemptsRequest):
    counts = {}
    latest = {}
    for attempt in sorted(request.attempts, key=lambda a: a.get('sequence', 0)):
        cid, status = attempt.get('course_id'), attempt.get('status')
        if cid and status in ('passed', 'failed', 'unknown'):
            if cid not in advisor.all_courses:
                continue
            counts.setdefault(cid, {'passed': 0, 'failed': 0, 'unknown': 0})[status] += 1
            latest[cid] = status
    return {'attempts': request.attempts, 'total_attempts': len(request.attempts),
            'course_summary': [{'course_id': cid, 'course_name': course_display(advisor, cid),
                                'passed_attempts': counts[cid]['passed'], 'failed_attempts': counts[cid]['failed'],
                                'unknown_attempts': counts[cid]['unknown'], 'latest_status': latest[cid]}
                               for cid in sorted(counts)]}

@app.post('/api/v1/recommendations', tags=['Recommendations'])
def v1_recommendations(request: RecommendationRequest):
    return recommend(request)

@app.post('/api/v1/recommendations/advisories', tags=['Advisories'])
def v1_advisories(request: AdvisoryRequest):
    return {'advisories': repeated_failure_advisories(request.attempts, advisor)}

@app.post('/api/v1/students/academic-summary', tags=['Academic Summary'])
def v1_academic_summary(request: StudentSummaryRequest):
    _check_course_codes(request.passed_courses, request.failed_courses)
    return {'academic_year': request.academic_year,
            'last_completed_semester': SEMESTERS.get(request.last_completed_semester),
            'target_semester': SEMESTERS[request.target_semester],
            'specialization': request.specialization, 'gpa': request.gpa,
            'passed_courses': request.passed_courses, 'failed_courses': request.failed_courses,
            'total_passed_hours': sum(int(advisor.courses.loc[c, 'Credits']) for c in set(request.passed_courses)),
            'total_failed_hours': sum(int(advisor.courses.loc[c, 'Credits']) for c in set(request.failed_courses)),
            'academic_warning': request.gpa < 2.0}

@app.post('/api/v1/registration/limits', tags=['Registration Limits'])
def v1_registration_limits(request: RegistrationRequest):
    first = request.academic_year == 1 and request.target_semester == 1 and request.last_completed_semester is None
    maximum = 18 if first or request.gpa >= 2.0 else sum(int(v) for v in advisor.courses['Credits'])
    return {'minimum_credits_required': 12, 'maximum_credits_allowed': maximum,
            'academic_warning': not first and request.gpa < 2.0,
            'note': 'This preserves the source Streamlit registration-limit behavior; verify against official bylaws.'}

@app.post('/api/v1/gpa/semester', tags=['Semester Gpa'])
def v1_semester_gpa(request: SemesterGPARequest):
    data = _gpa_data(request.grades)
    return {key: data[key] for key in ('courses', 'semester_gpa', 'semester_average_percentage', 'semester_credit_hours', 'total_quality_points', 'note')}

@app.post('/api/v1/gpa/cumulative', tags=['Cumulative Gpa'])
def v1_cumulative_gpa(request: CumulativeGPARequest):
    return _gpa_data(request.grades, request.previous_gpa, request.previous_hours)

@app.post('/api/v1/recommendations/export', tags=['Export Recommendations'])
def v1_export(request: ExportRequest):
    return export_pdf(request)
