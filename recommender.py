"""
Edu Advisor - Recommendation Engine
Fayoum University - Faculty of Computers and Information
Full Implementation - Manual Data Entry
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
import json
import pandas as pd


@dataclass
class StudentInput:
    """Student data input structure"""
    student_id: str
    current_level: int
    completed_credits: int
    # Kept for backward compatibility only. The engine recalculates GPA from grades.
    gpa: Optional[float] = None
    specialization: str = ""
    passed_courses: List[str] = field(default_factory=list)
    failed_courses: List[str] = field(default_factory=list)
    # Final grade per course, e.g. {"BS101": "A", "CS101": "B+"}.
    grades: Dict[str, str] = field(default_factory=dict)
    # Courses passed after a retake; their counted grade is capped at D (2.0 points).
    retaken_courses: List[str] = field(default_factory=list)


@dataclass
class Recommendation:
    course_id: str
    course_name: str
    credits: int
    level: int
    course_type: str
    category: str
    score: float
    reasons: List[str]
    is_retake: bool = False
    prerequisites_met: bool = True
    missing_prerequisites: List[str] = field(default_factory=list)


class EduAdvisor:
    """Main recommendation engine - takes student input and returns recommendations"""

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor____init__.txt
    def __init__(self, data_dir: str | Path = None):
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent / "data"
        self._load_all_data()
        self._build_indexes()

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___load_all_data.txt
    def _load_all_data(self) -> None:
        """Load all data from JSON files"""
        # Load courses
        courses_file = self.data_dir / "bylaws_courses.json"
        with open(courses_file, 'r', encoding='utf-8') as f:
            courses_data = json.load(f)
        
        courses_list = []
        for code, info in courses_data.items():
            courses_list.append({
                "Course_ID": code,
                "Course_Name": info.get("name_en", info.get("name", "")),
                "Course_Name_Arabic": info.get("name_ar", info.get("arabic_name", info.get("name_arabic", ""))),
                "Credits": info["credits"],
                "Level": info["level"],
                "Type": self._normalize_course_type(info.get("type", "Required")),
                "Category": info.get("category", "Other"),
                "Specialization": info.get("specialization", info.get("specializations", [])),
            })
        self.courses = pd.DataFrame(courses_list).set_index("Course_ID")
        
        # Load prerequisites
        prereq_file = self.data_dir / "bylaws_prerequisites.json"
        with open(prereq_file, 'r', encoding='utf-8') as f:
            prereq_data = json.load(f)
        
        prereq_list = []
        for course, prereqs in prereq_data.items():
            for p in prereqs:
                prereq_list.append({"Course_ID": course, "Prerequisite_ID": p})
        self.prereq = pd.DataFrame(prereq_list, columns=["Course_ID", "Prerequisite_ID"])
        
        # Load rules
        rules_file = self.data_dir / "bylaws_rules.json"
        with open(rules_file, 'r', encoding='utf-8') as f:
            self.rules = json.load(f)

        # Use the supplied bylaws grade-point table; fallback keeps the engine usable
        # before these keys are added to bylaws_rules.json.
        self.grade_points = self.rules.get("grade_points", {
            "A+": 4.0, "A": 3.6, "B+": 3.3, "B": 3.0,
            "C+": 2.6, "C": 2.4, "D+": 2.2, "D": 2.0, "F": 0.0,
        })

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___normalize_course_type.txt
    @staticmethod
    def _normalize_course_type(value) -> str:
        """Use the requested catalog label for elective/selective courses."""
        text = str(value or "Required").strip()
        return "Selective" if text.casefold().startswith(("elective", "selective")) else text

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___category_priority.txt
    @staticmethod
    def _category_priority(category: str) -> int:
        """Lower values represent earlier curriculum requirement groups."""
        value = str(category or "").casefold().replace("_", " ").replace("-", " ")
        if any(term in value for term in ("general", "general education", "general requirement", "faculty requirement", "faculty requirements")) or value.strip() in {"faculty", "faculty requirements"}:
            return 0
        if any(term in value for term in ("basic science", "basic sciences", "science requirement")):
            return 1
        if any(term in value for term in ("basic computing", "computing requirement", "computing", "computer requirement")):
            return 2
        if any(term in value for term in ("specialization", "specialisation", "major", "is required", "cs required", "ai required")):
            return 3
        if "university" in value:
            return 4
        if any(term in value for term in ("project", "training", "graduation project")):
            return 5
        return 6

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___specialization_matches.txt
    @staticmethod
    def _specialization_matches(course, specialization: str, course_id: str) -> bool:
        """Filter specialization-tagged courses when the catalog provides tags."""
        selected = str(specialization or "General").strip().upper()
        if selected in {"", "GENERAL"}:
            return True
        raw = course.get("Specialization", [])
        if isinstance(raw, str):
            tags = {part.strip().upper() for part in raw.replace("/", ",").replace(";", ",").split(",") if part.strip()}
        elif isinstance(raw, (list, tuple, set)):
            tags = {str(part).strip().upper() for part in raw if str(part).strip()}
        else:
            tags = set()
        if tags:
            return selected in tags or "GENERAL" in tags or "ALL" in tags
        category = str(course.get("Category", "")).upper()
        # Honor an explicit specialization in the category; otherwise keep the
        # course because the existing catalog may not yet have specialization tags.
        for code in ("IS", "CS", "AI"):
            if code in category and any(word in category for word in ("SPECIAL", "REQUIRED", "MAJOR")):
                return selected == code
        if "SPECIALIZATION" in category or "SPECIALISATION" in category or "MAJOR" in category:
            normalized_id = str(course_id).strip().upper()
            code_prefix = next((code for code in ("IS", "CS", "AI") if normalized_id.startswith(code)), None)
            if code_prefix:
                return selected == code_prefix
        return True

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___build_indexes.txt
    def _build_indexes(self) -> None:
        """Build indexes for fast lookups"""
        self.prereq_map: Dict[str, List[str]] = (
            self.prereq.groupby("Course_ID")["Prerequisite_ID"].apply(list).to_dict()
        )
        
        self.unlocks: Dict[str, List[str]] = {}
        for course, prereqs in self.prereq_map.items():
            for p in prereqs:
                self.unlocks.setdefault(p, []).append(course)
        
        self.all_courses = set(self.courses.index)
        
        # Build category mappings
        self.category_courses: Dict[str, List[str]] = {}
        for course_id, row in self.courses.iterrows():
            category = row.get("Category", "Other")
            self.category_courses.setdefault(category, []).append(course_id)

    # ============================================================
    # GPA CALCULATION
    # ============================================================

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__calculate_gpa.txt
    def calculate_gpa(self, student: StudentInput) -> Optional[float]:
        """Calculate weighted GPA from course grades and catalog credit hours.

        `student.grades` must map course IDs to final letter grades. Courses without
        a supplied grade are not guessed or treated as zero. Returns None when no
        valid graded courses are available.
        """
        weighted_points = 0.0
        total_graded_credits = 0
        retaken = set(student.retaken_courses)

        for raw_course_id, raw_grade in student.grades.items():
            course_id = str(raw_course_id).strip()
            if course_id not in self.all_courses:
                raise ValueError(f"Unknown course in grades: {course_id}")

            grade = str(raw_grade).strip().upper()
            if grade not in self.grade_points:
                raise ValueError(
                    f"Unknown grade '{raw_grade}' for course {course_id}. "
                    f"Allowed grades: {', '.join(self.grade_points.keys())}"
                )

            points = float(self.grade_points[grade])

            # Bylaw rule provided by the user: a course failed previously and then
            # passed on retake is counted as 62%, equivalent here to grade D = 2.0.
            if course_id in retaken and grade != "F":
                points = min(points, float(self.grade_points.get("D", 2.0)))

            credits = int(self.courses.loc[course_id, "Credits"])
            weighted_points += points * credits
            total_graded_credits += credits

        if total_graded_credits == 0:
            return None
        return round(weighted_points / total_graded_credits, 4)

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__get_overall_grade.txt
    def get_overall_grade(self, gpa: Optional[float]) -> Optional[str]:
        """Return the overall grade label configured in bylaws_rules.json."""
        if gpa is None:
            return None
        ranges = self.rules.get("overall_grade", {})
        for label, bounds in ranges.items():
            if float(bounds.get("min", 0)) <= gpa <= float(bounds.get("max", 4)):
                return label
        # Protect against small rounding gaps in configured ranges.
        if gpa >= 3.6:
            return "Excellent"
        if gpa >= 3.0:
            return "Very Good"
        if gpa >= 2.4:
            return "Good"
        if gpa >= 2.0:
            return "Acceptable"
        return "Fail"

    # ============================================================
    # VALIDATION & AVAILABILITY METHODS
    # ============================================================

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__validate_courses.txt
    def validate_courses(self, course_codes: List[str]) -> Tuple[bool, List[str], List[str]]:
        """
        Validate course codes against the database.
        Returns: (is_valid, valid_courses, invalid_courses)
        """
        valid = []
        invalid = []
        for code in course_codes:
            if code in self.all_courses:
                valid.append(code)
            else:
                invalid.append(code)
        return len(invalid) == 0, valid, invalid

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__get_course_availability.txt
    def get_course_availability(self, course_id: str) -> Dict:
        """
        Check if a course is available in which semesters.
        Returns: {available: bool, semesters: List[int], reason: str}
        """
        if course_id not in self.all_courses:
            return {
                "available": False,
                "semesters": [],
                "reason": f" Course {course_id} not found"
            }
        
        course = self.courses.loc[course_id]
        course_level = int(course["Level"])
        
        # All courses available in Fall (1) and Spring (2)
        available_semesters = [1, 2]
        
        # Level 4 courses also available in Summer (3)
        if course_level == 4:
            available_semesters.append(3)
        
        return {
            "available": True,
            "semesters": available_semesters,
            "reason": f"Available in semesters: {', '.join(map(str, available_semesters))}"
        }

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__get_failed_courses_status.txt
    def get_failed_courses_status(self, student: StudentInput, current_semester: int = 1) -> Dict:
        """
        Check failed courses and when they can be retaken.
        """
        failed_courses_status = {}
        for course_id in student.failed_courses:
            if course_id not in self.all_courses:
                failed_courses_status[course_id] = {
                    "course_id": course_id,
                    "course_name": " UNKNOWN COURSE",
                    "available": False,
                    "available_semesters": [],
                    "can_retake_now": False,
                    "prerequisites_met": False,
                    "missing_prerequisites": [],
                    "recommendation": f" Course {course_id} not found in system"
                }
                continue
            
            availability = self.get_course_availability(course_id)
            # Check if student meets prerequisites for retake
            met, missing = self._prerequisites_met(course_id, set(student.passed_courses))
            
            failed_courses_status[course_id] = {
                "course_id": course_id,
                "course_name": self.courses.loc[course_id]["Course_Name"],
                "available": availability["available"],
                "available_semesters": availability["semesters"],
                "can_retake_now": current_semester in availability["semesters"],
                "prerequisites_met": met,
                "missing_prerequisites": missing,
                "recommendation": self._get_failed_course_recommendation(
                    course_id, current_semester, availability, met
                )
            }
        return failed_courses_status

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___get_failed_course_recommendation.txt
    def _get_failed_course_recommendation(self, course_id: str, current_semester: int, 
                                          availability: Dict, prereq_met: bool) -> str:
        """Generate recommendation for failed course"""
        if not prereq_met:
            return f" Cannot retake {course_id} - Missing prerequisites"
        if current_semester in availability["semesters"]:
            return f" {course_id} is available this semester - RECOMMENDED TO RETAKE"
        else:
            next_semester = min([s for s in availability["semesters"] if s > current_semester] or availability["semesters"])
            return f" {course_id} will be available in Semester {next_semester}"

    # ============================================================
    # CORE RECOMMENDATION METHODS
    # ============================================================

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___prerequisites_met.txt
    def _prerequisites_met(self, course_id: str, passed: Set[str]) -> Tuple[bool, List[str]]:
        """Check if all prerequisites are met, return (met, missing_list)"""
        required = self.prereq_map.get(course_id, [])
        missing = [p for p in required if p not in passed]
        return len(missing) == 0, missing

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___check_eligibility.txt
    def _check_eligibility(self, course_id: str, student: StudentInput, passed: Set[str]) -> Tuple[bool, List[str]]:
        """Check if a course is eligible for the student"""
        # Check if already passed
        if course_id in passed:
            return False, ["Already passed"]
        
        # A failed course that is offered this semester is a mandatory retake.
        # It remains eligible even if transcript data is missing an old prerequisite.
        if course_id in student.failed_courses:
            return True, ["Mandatory retake: failed course available this semester"]

        # Check prerequisites for new courses.
        met, missing = self._prerequisites_met(course_id, passed)
        if not met:
            return False, [f"Missing prerequisites: {', '.join(missing)}"]

        # No level-based exclusion: courses from every level can be considered.
        return True, []

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___score_course.txt
    def _score_course(self, course_id: str, student: StudentInput, passed: Set[str]) -> Tuple[float, List[str], bool]:
        """Score a course based on student profile and bylaws rules"""
        course = self.courses.loc[course_id]
        score = 0.0
        reasons = []
        is_retake = course_id in student.failed_courses

        # 1. RETAKE - Highest priority (bylaws Article 17, 23)
        if is_retake:
            score += 100
            reasons.append(" Retake failed course (highest priority)")

        # 2. COURSE TYPE (bylaws Article 24)
        if course["Type"] == "Required":
            score += 40
            reasons.append(" Required course")
        else:
            score += 10
            reasons.append(" Selective course")

        # 3. LEVEL APPROPRIATENESS (bylaws Article 4)
        level_diff = int(course["Level"]) - student.current_level
        if level_diff == 0:
            score += 25
            reasons.append(" Same level")
        elif level_diff == 1:
            score += 15
            reasons.append("Next level (natural progress)")
        elif level_diff < 0:
            score += 5
            reasons.append("Lower level (fill gaps)")

        # 4. GPA-BASED RULES (bylaws Article 16, 19)
        min_gpa = self.rules.get("min_gpa_for_graduation", 2.0)
        
        calculated_gpa = student.gpa if student.gpa is not None else self.calculate_gpa(student)
        if calculated_gpa is not None and calculated_gpa < min_gpa:  # Low GPA
            if is_retake or int(course["Level"]) <= student.current_level:
                score += 15
                reasons.append("Suitable for low GPA")
            else:
                score -= 20
                reasons.append(" May be difficult with current GPA")
        elif calculated_gpa is not None and calculated_gpa >= 3.0:  # High GPA
            if int(course["Level"]) == student.current_level + 1:
                score += 10
                reasons.append(" Suitable for high GPA")

        # 5. UNLOCKS FUTURE COURSES (bylaws Article 8)
        unlock_count = len(self.unlocks.get(course_id, []))
        if unlock_count > 0:
            score += min(unlock_count * 3, 15)
            reasons.append(f" Unlocks {unlock_count} future course(s)")

        # 6. CREDIT HOURS (bylaws Article 4)
        if int(course["Credits"]) == 3:
            score += 3
        elif int(course["Credits"]) == 2:
            score += 1

        # 7. GRADUATION PROGRESS (bylaws Article 24)
        total_required = self.rules.get("total_credits_required", 144)
        if student.completed_credits >= total_required - 30 and int(course["Level"]) >= 3:
            score += 10
            reasons.append(" Nearing graduation")

        # 8. CATEGORY BALANCE (bylaws Article 24)
        category = course.get("Category", "Other")
        if category in self.rules.get("requirements", {}):
            req_key = category.lower().replace(" ", "_")
            if req_key in self.rules["requirements"]:
                req = self.rules["requirements"][req_key]
                if req.get("courses") and course_id in req["courses"]:
                    score += 5
                    reasons.append(f" {category} requirement")

        return score, reasons, is_retake

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__recommend.txt
    def recommend(
        self, student: StudentInput, max_credits: int = 18, min_credits: int = 12,
        top_n: int = 8, current_semester: int = 1
    ) -> Dict:
        """
        Main recommendation method.
        
        Args:
            student: StudentInput object with student data
            max_credits: Maximum credits to recommend
            min_credits: Minimum credits to recommend
            top_n: Maximum number of courses to recommend
        
        Returns:
            Dictionary with recommendations and status
        """
        # Use the student's current GPA when provided. If no GPA was supplied,
        # fall back to calculating it from recorded course grades.
        calculated_gpa = self.calculate_gpa(student) if student.gpa is None else None
        if calculated_gpa is not None:
            student.gpa = calculated_gpa

        # Convert passed courses to set for faster lookup
        passed = set(student.passed_courses)
        
        # Check prerequisites for all courses and find eligible ones
        candidates = []
        for course_id in sorted(self.all_courses):
            # Only recommend courses available in the selected semester.
            availability = self.get_course_availability(course_id)
            if current_semester not in availability["semesters"]:
                continue
            course = self.courses.loc[course_id]
            if not self._specialization_matches(course, student.specialization, course_id):
                continue
            eligible, eligibility_reasons = self._check_eligibility(course_id, student, passed)
            if eligible:
                # Score is internal to the engine; user-facing ordering is by
                # mandatory retake status and curriculum requirement category.
                score, score_reasons, is_retake = self._score_course(course_id, student, passed)
                category = course.get("Category", "Other")
                priority = self._category_priority(category)
                reasons = list(score_reasons)
                if is_retake:
                    reasons.insert(0, "Mandatory retake: failed course available this semester")
                candidates.append({
                    "course_id": course_id,
                    "course_name": course["Course_Name"],
                    "course_name_ar": course.get("Course_Name_Arabic", ""),
                    "credits": int(course["Credits"]),
                    "level": int(course["Level"]),
                    "type": course["Type"],
                    "category": category,
                    "category_priority": priority,
                    "score": score,
                    "reasons": reasons,
                    "is_retake": is_retake,
                    "prerequisites_met": True,
                })

        # Mandatory failed courses available this semester come first. Other
        # courses follow the requested category priority, then internal score.
        candidates.sort(key=lambda x: (not x["is_retake"], x["category_priority"], -x["score"], x["course_id"]))

        # Mandatory retakes are always included, even if they exceed max_credits
        # or top_n; the system must not omit a failed course offered this term.
        selected = [rec for rec in candidates if rec["is_retake"]]
        total_credits = sum(rec["credits"] for rec in selected)
        selected_ids = {rec["course_id"] for rec in selected}

        for rec in candidates:
            if rec["course_id"] in selected_ids:
                continue
            if len(selected) >= top_n:
                break
            if total_credits + rec["credits"] > max_credits:
                continue
            selected.append(rec)
            selected_ids.add(rec["course_id"])
            total_credits += rec["credits"]

        # If we couldn't reach min_credits, try to add more
        if total_credits < min_credits:
            for rec in candidates:
                if rec["course_id"] in selected_ids:
                    continue
                if total_credits + rec["credits"] > max_credits:
                    continue
                selected.append(rec)
                selected_ids.add(rec["course_id"])
                total_credits += rec["credits"]
                if total_credits >= min_credits or len(selected) >= top_n:
                    break

        # Check graduation eligibility
        graduation_eligible = self._check_graduation_eligibility(student)
        
        # Check academic warning status
        min_gpa = self.rules.get("min_gpa_for_graduation", 2.0)
        academic_warning = (student.gpa is not None and student.gpa < min_gpa)
        
        # Get remaining credits to graduation
        total_required = self.rules.get("total_credits_required", 144)
        remaining_credits = max(0, total_required - student.completed_credits)

        return {
            "student": {
                "student_id": student.student_id,
                "current_level": student.current_level,
                "current_semester": current_semester,
                "completed_credits": student.completed_credits,
                "gpa": student.gpa,
                "overall_grade": self.get_overall_grade(student.gpa),
                "gpa_calculated_from_grades": student.gpa is not None,
                "specialization": student.specialization or "Not selected",
                "passed_courses_count": len(student.passed_courses),
                "failed_courses_count": len(student.failed_courses),
                "failed_courses": student.failed_courses,
            },
            "status": {
                "graduation_eligible": graduation_eligible,
                "academic_warning": academic_warning,
                "remaining_credits": remaining_credits,
                "candidates_found": len(candidates),
            },
            "total_recommended_credits": total_credits,
            "recommendations": [
                {
                    "rank": i + 1,
                    "course_id": r["course_id"],
                    "course_name": r["course_name"],
                    "course_name_ar": r.get("course_name_ar", ""),
                    "course_name_display": " / ".join(part for part in [str(r.get("course_name_ar", "")).strip(), str(r["course_name"]).strip()] if part),
                    "credits": r["credits"],
                    "level": r["level"],
                    "type": r["type"],
                    "category": r["category"],
                    "score": r["score"],
                    "is_retake": r["is_retake"],
                    "reasons": r["reasons"],
                }
                for i, r in enumerate(selected)
            ],
            "bylaws_info": {
                "institution": self.rules.get("institution", "Fayoum University"),
                "faculty": self.rules.get("faculty", "Faculty of Computers and Information"),
                "year": self.rules.get("year", 2019),
                "total_credits_required": self.rules.get("total_credits_required", 144),
                "min_gpa": self.rules.get("min_gpa_for_graduation", 2.0),
                "semester_min_credits": self.rules.get("semester_limits", {}).get("min_credits", 12),
                "semester_max_credits": self.rules.get("semester_limits", {}).get("max_credits", 18),
                "level_names": self.rules.get("level_names", {}),
            },
            "requirements_breakdown": {
                "university": self.rules.get("requirements", {}).get("university", {}),
                "faculty": self.rules.get("requirements", {}).get("faculty", {}),
                "basic_sciences": self.rules.get("requirements", {}).get("basic_sciences", {}),
                "basic_computing": self.rules.get("requirements", {}).get("basic_computing", {}),
                "specialization": self.rules.get("requirements", {}).get("specialization", {}),
                "projects_training": self.rules.get("requirements", {}).get("projects_training", {}),
            }
        }

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor___check_graduation_eligibility.txt
    def _check_graduation_eligibility(self, student: StudentInput) -> bool:
        """Check if student is eligible for graduation"""
        total_required = self.rules.get("total_credits_required", 144)
        min_gpa = self.rules.get("min_gpa_for_graduation", 2.0)
        
        if (student.completed_credits >= total_required
                and student.gpa is not None and student.gpa >= min_gpa):
            return True
        return False

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__get_course_info.txt
    def get_course_info(self, course_id: str) -> Optional[Dict]:
        """Get detailed information about a specific course"""
        if course_id not in self.courses.index:
            return None
        
        course = self.courses.loc[course_id]
        prereqs = self.prereq_map.get(course_id, [])
        unlocks = self.unlocks.get(course_id, [])
        
        return {
            "course_id": course_id,
            "course_name": course["Course_Name"],
            "course_name_ar": course.get("Course_Name_Arabic", ""),
            "course_name_display": " / ".join(part for part in [str(course.get("Course_Name_Arabic", "")).strip(), str(course["Course_Name"]).strip()] if part),
            "credits": int(course["Credits"]),
            "level": int(course["Level"]),
            "type": course["Type"],
            "category": course.get("Category", "Other"),
            "prerequisites": prereqs,
            "unlocks": unlocks,
        }

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__get_all_courses.txt
    def get_all_courses(self) -> List[Dict]:
        """Get all courses with their information"""
        courses = []
        for course_id in sorted(self.all_courses):
            info = self.get_course_info(course_id)
            if info:
                courses.append(info)
        return courses

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__search_courses_by_name.txt
    def search_courses_by_name(self, search_term: str) -> List[Dict]:
        """Search course names case-insensitively; returns course dictionaries."""
        term = str(search_term).strip().casefold()
        if not term:
            return []
        results = []
        for course_id in sorted(self.all_courses):
            info = self.get_course_info(course_id)
            if info and term in str(info["course_name"]).casefold():
                results.append(info)
        return results

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__search_course_by_name.txt
    def search_course_by_name(self, search_term: str) -> Optional[str]:
        """Return the closest simple substring match as a course ID, if any."""
        term = str(search_term).strip().casefold()
        if not term:
            return None
        # Prefer exact course-code matches, then names containing the query.
        if search_term in self.all_courses:
            return search_term
        matches = self.search_courses_by_name(search_term)
        return matches[0]["course_id"] if matches else None

    # https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/EduAdvisor__print_recommendation.txt
    def print_recommendation(self, student: StudentInput, **kwargs) -> None:
        """Print recommendations in a formatted way"""
        result = self.recommend(student, **kwargs)
        
        print("=" * 80)
        print(f" Edu Advisor - Recommendations for Student: {result['student']['student_id']}")
        print(f" {result['bylaws_info']['institution']}")
        print(f" {result['bylaws_info']['faculty']} (Bylaws {result['bylaws_info']['year']})")
        print("=" * 80)
        
        # Status indicators
        if result['status']['graduation_eligible']:
            print("STATUS: ELIGIBLE FOR GRADUATION ")
        if result['status']['academic_warning']:
            print("ACADEMIC WARNING: GPA below minimum requirement")
        print("-" * 80)
        
        # Student info
        level_name = result['bylaws_info'].get('level_names', {}).get(str(result['student']['current_level']), '')
        print(f" GPA              : {result['student']['gpa']:.2f} (Min: {result['bylaws_info']['min_gpa']})")
        print(f" Current Level    : {result['student']['current_level']} ({level_name})")
        print(f" Completed Credits: {result['student']['completed_credits']} / {result['bylaws_info']['total_credits_required']}")
        print(f" Specialization   : {result['student']['specialization']}")
        print(f" Remaining Credits: {result['status']['remaining_credits']}")
        print(f" Failed Courses   : {len(result['student']['failed_courses'])} courses")
        if result['student']['failed_courses']:
            print(f"   Failed: {', '.join(result['student']['failed_courses'])}")
        print(f" Total Recommended: {result['total_recommended_credits']} credits")
        print("-" * 80)

        if not result["recommendations"]:
            print("No suitable courses found.")
            print("   Check: prerequisites, passed courses, or credit limits")
            return

        print("RECOMMENDED COURSES:")
        print()
        for rec in result["recommendations"]:
            retake_flag = " [RETAKE]" if rec["is_retake"] else ""
            course_display = rec.get("course_name_display", rec["course_name"])
            print(f" #{rec['rank']:2}. {rec['course_id']} - {course_display}{retake_flag}")
            print(f"     Credits: {rec['credits']} | Type: {rec['type']} | Category: {rec['category']}")
            print(f"     {' | '.join(rec['reasons'])}")
            print()
        print("=" * 80)
        
        # Show requirements breakdown
        print("\nREQUIREMENTS BREAKDOWN:")
        print("-" * 40)
        for key, value in result['requirements_breakdown'].items():
            if isinstance(value, dict) and "total_credits" in value:
                print(f"  {key.replace('_', ' ').title()}: {value['total_credits']} credits")
        print("=" * 80)


# ============================================================
# Helper function to create student input
# ============================================================

# https://github.com/ABDELRHMAN4004/Edu-Advisor---Recommendation/blob/master/explain/docs/functions/recommender/create_student_input.txt

def create_student_input(
    student_id: str,
    current_level: int,
    completed_credits: int,
    gpa: Optional[float] = None,
    specialization: str = "",
    passed_courses: List[str] = None,
    failed_courses: List[str] = None,
    grades: Dict[str, str] = None,
    retaken_courses: List[str] = None
) -> StudentInput:
    """
    Helper function to create a StudentInput object.
    
    Example:
        student = create_student_input(
            student_id="S0001",
            current_level=2,
            completed_credits=42,
            gpa=2.8,
            specialization="CS",
            passed_courses=["BS101", "BS102", "CS101", "CS141"],
            failed_courses=["BS103"]
        )
    """
    return StudentInput(
        student_id=student_id,
        current_level=current_level,
        completed_credits=completed_credits,
        gpa=gpa,
        specialization=specialization,
        passed_courses=passed_courses or [],
        failed_courses=failed_courses or [],
        grades=grades or {},
        retaken_courses=retaken_courses or [],
    )


# ============================================================
# Main - Example Usage
# ============================================================

if __name__ == "__main__":
    import sys
    import io
    
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    
    # Initialize the recommender
    script_dir = Path(__file__).resolve().parent
    advisor = EduAdvisor(data_dir=script_dir / "data")
    
    print("=" * 80)
    print("  EDU ADVISOR - RECOMMENDATION ENGINE")
    print("=" * 80)
    print(f" Institution: {advisor.rules.get('institution', 'N/A')}")
    print(f" Faculty: {advisor.rules.get('faculty', 'N/A')}")
    print(f" Total Courses: {len(advisor.all_courses)}")
    print(f" Total Credits Required: {advisor.rules.get('total_credits_required', 144)}")
    print("=" * 80)
    print()
    
    # ============================================================
    # EXAMPLE 1: Student with low GPA and failed courses
    # ============================================================
    print(" EXAMPLE 1: Level 3 Student (Low GPA, Failed Courses)")
    print("-" * 40)
    
    student = create_student_input(
        student_id="S2023001",
        current_level=3,
        completed_credits=45,
        gpa=None,
        grades={},  # Add the student's final letter grade for each graded course here.
        specialization="CS",
        passed_courses=[
            "BS101", "BS102", "BS103", "BS104", "BS105",
            "CS101", "CS102", "CS141", "CS142",
            "IS201", "BS201", "UNI001", "UNI002",
            "UNI005", "UNI006", "UNI011", "BS111", "BS112", "BS133"
        ],
        failed_courses=[
            "CS211", "CS241", "IS211", "BS202", "CS202", "CS203"
        ]
    )
    advisor.print_recommendation(student, max_credits=18, min_credits=12, top_n=8)
    
    print("\n" * 2)
    
    # ============================================================
    # EXAMPLE 2: Show failed courses status
    # ============================================================
    print(" EXAMPLE 2: Failed Courses Status")
    print("-" * 40)
    
    failed_status = advisor.get_failed_courses_status(student, current_semester=2)
    for course_id, status in failed_status.items():
        print(f"  {course_id} - {status['course_name']}")
        print(f"    Available: {'Yes' if status['can_retake_now'] else 'No'} Semester {status['available_semesters']}")
        print(f"    {status['recommendation']}")
        print()
    
    # ============================================================
    # EXAMPLE 3: Validate courses
    # ============================================================
    print("EXAMPLE 3: Validate Courses")
    print("-" * 40)
    
    test_courses = ["BS101", "CS999", "CS101", "UNI001"]
    is_valid, valid, invalid = advisor.validate_courses(test_courses)
    print(f"  Valid courses: {valid}")
    print(f"  Invalid courses: {invalid}")
    print(f"  All valid: {'Yes' if is_valid else 'No'}")