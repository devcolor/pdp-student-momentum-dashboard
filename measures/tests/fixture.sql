-- Plain SQL that runs on SQLite and PostgreSQL.
-- A tiny database with only the tables and columns the measures read. 48 made-up students.
--
--   2022-23  students 1-24   retention: 1-16 yes, 17-20 no, 21-24 blank      persistence: 1, 17-20 yes
--   2023-24  students 25-36  retention: 25-30 yes, 31-36 no
--   2024-25  students 37-48  no answers yet
--
-- Fall starters are 1-14 and 25-48, spring starters 15-24. Pell is yes for 1-12, no for 13-24.
-- Age is "> 20-24" (written the way the mock file spells it) for 1-12.
--
-- Gateway completed flag (C completed, D did not complete). Students not required have NA or a blank.
--   Math 2022-23:    1-12 C   13-20 D (17-20 never took it)   21-22 not required   23 requirement unknown
--                    24 required but blank     12 of 20, 2 left out (23-24), 2 out of scope (21-22).
--   Math 2023-24:    25-30 C   31-36 D     6 of 12.
--   English 2022-23: 1-10 C   11-24 D     10 of 24.
--   English 2023-24: 25-36 C.
--   2024-25: blank for both, so nothing is observable yet.
-- Students 45-48 have a pell value that isn't on the list ('U') and a blank enrollment type, and
-- first gen is blank for everyone, so each of those lands in an UNKNOWN group.
--
-- Year 1 credits attempted / earned, for credit completion. Students 21-22 are Re-admit (out of scope),
-- 23-24 Transfer-In, the rest First-time. 2024-25 has no credits yet.
--   2022-23: 1-10 15/15 (ratio 1)   11-16 3/0 (ratio 0)   17-18 blank   19 0/0   20 12/12 but full- or part-time unknown
--            21-22 12/12 re-admit   23-24 12/6 (ratio 0.5)
--     18 students counted, ratios add up to 11, so the rate is 11 / 18 = 0.6111. Pooled credits would give 162 / 192 = 0.84.
--   2023-24: 25-36 10/5 (ratio 0.5)     6 of 12.
--
-- Course enrollments, for DFW (grades are text, as in the data):
--   2022-23 students 1-24 have one class each. Grades: 1-8 "4", 9-10 "3.7", 11 "2.0", 12 "2", 13 "3",
--     14 "2.3", 15 "1.0", 16 "1.7", 17 "1", 18 "0.3", 19-20 "F", 21 "W", 22 "I", 23 "A" (audit), 24 "P".
--   Students 1-3 also have a second class graded "W", and student 1 has a row with no class at all.
--   Courses: 1 ENGL 1302 (nearly every class), 2 MATH 1314 (the second classes of students 1-3), 3 BIOL 1101 and
--     4 HIST 1301 (only the 2023-24 classes).
--   2023-24 students 25-27 have four classes each, graded "P": 12 enrollments from only 3 students.
--   2024-25 students 37-48 have one class each, graded "I", so nobody has a final grade yet.
--   Every class is in its cohort year's fall term (911, 912, 913) and section 01.
--
-- Midterm grades, for the midterm measures, on the 2022-23 ENGL 1302 classes only:
--   1-8 A, 9-11 B, 12-14 D, 15-18 L, 19 D, 20 L, 21 W (withdrew before midterm), 22 D, 23 none, 24 L.
--   Alert 2022-23: 21 is out of scope. 23 and the three MATH 1314 classes have no midterm grade, so they are
--     left out (4). 11 of the other 22 are D or L: 11 / 22 = 0.5.
--   Recovery 2022-23: the 11 alerts. 22's final grade is incomplete, so it is left out. 12, 13, 14 and 24
--     passed (2, 3, 2.3, P): 4 / 10.
--   2023-24 and 2024-25 have no midterm grades, so neither is observable yet.
--
-- Student matrix rows, for the first-fall measures (fall terms 911 2022-23, 912 2023-24, 913 2024-25):
--   2022-23: 1-12 have a row for fall 2022. Retention to spring: 1-8 still_enrolled, 9-10 not_returning,
--     11-12 blank. Standing: 1-7 good, 8-10 not good, 11-12 blank. Fall starters 13-14 have no fall 2022 row
--     (13 has a spring row, which doesn't count), so with spring starters 15-24 there are 12 out of scope.
--     Retention 8 / 10, good standing 7 / 10.
--   Student 1 also has a fall 2023 row (not_returning, not good) and 15 a fall 2023 row: neither is a first fall.
--   2023-24: 25-36. Retention 25-34 still_enrolled, 35-36 not_returning: 10 / 12. Standing all good: 12 / 12.
--   2024-25: 37-40 have a fall 2024 row with blank answers, so nothing is observable yet.
--   Educational goal (from the earliest row): 1-6 graduate_and_transfer, 7-12 no_declaration, 13 and 15
--     graduate_and_find_job, 25-36 take_classes_and_transfer. Student 1's later row says personal_enrichment.
--     Everyone else, and 37-40 (blank), is UNKNOWN.

CREATE TABLE student (
    student_id TEXT, student_age TEXT, race TEXT, ethnicity TEXT, gender TEXT, first_gen TEXT
);
CREATE TABLE cohort_membership (
    student_id TEXT, cohort TEXT, cohort_term TEXT, enrollment_type TEXT,
    enrollment_intensity_first_term TEXT, pell_status_first_year TEXT,
    retention BOOLEAN, persistence BOOLEAN,
    completed_gateway_math_year1 TEXT, completed_gateway_english_year1 TEXT,
    gateway_math_status TEXT, gateway_english_status TEXT,
    number_of_credits_attempted_yr_1 REAL, number_of_credits_earned_yr_1 REAL
);
CREATE TABLE course (course_id INTEGER, course_prefix TEXT, course_number TEXT);
CREATE TABLE course_enrollment (student_id TEXT, cohort TEXT, course_id INTEGER, grade TEXT, term_id INTEGER, section_id TEXT);
CREATE TABLE data_provider (provider_id INTEGER, source_file TEXT, file_sha256 TEXT, loaded_at TEXT);

INSERT INTO data_provider VALUES (1, 'fixture.sql', 'not-a-real-hash', '2026-01-01T00:00:00');

-- n holds the numbers 1 to 48, one per student.
CREATE TEMP TABLE n AS
WITH RECURSIVE numbers(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM numbers WHERE i < 48)
SELECT i FROM numbers;

INSERT INTO student
SELECT CASE WHEN i < 10 THEN 's0' || i ELSE 's' || i END,
       CASE WHEN i <= 12 THEN '>20 - 24' ELSE 'Older than 24' END,
       'White', 'N', 'F', NULL
FROM n;

INSERT INTO cohort_membership
SELECT CASE WHEN i < 10 THEN 's0' || i ELSE 's' || i END,
       CASE WHEN i <= 24 THEN '2022-23' WHEN i <= 36 THEN '2023-24' ELSE '2024-25' END,
       CASE WHEN i BETWEEN 15 AND 24 THEN 'SPRING' ELSE 'FALL' END,
       CASE
           WHEN i >= 45 THEN NULL
           WHEN i BETWEEN 21 AND 22 THEN 'Re-admit'
           WHEN i BETWEEN 23 AND 24 THEN 'Transfer-In'
           ELSE 'First-time'
       END,
       CASE WHEN i = 20 THEN NULL ELSE 'Full-time' END,
       CASE WHEN i BETWEEN 45 AND 48 THEN 'U' WHEN i BETWEEN 13 AND 24 THEN 'N' ELSE 'Y' END,
       CASE
           WHEN i <= 16 THEN TRUE
           WHEN i <= 20 THEN FALSE
           WHEN i <= 24 THEN NULL
           WHEN i <= 30 THEN TRUE
           WHEN i <= 36 THEN FALSE
           ELSE NULL
       END,
       CASE
           WHEN i IN (1, 17, 18, 19, 20) THEN TRUE
           WHEN i <= 36 AND (i < 21 OR i > 24) THEN FALSE
           ELSE NULL
       END,
       CASE
           WHEN i <= 12 THEN 'C'
           WHEN i <= 20 THEN 'D'
           WHEN i <= 22 THEN 'NA'
           WHEN i <= 24 THEN NULL
           WHEN i <= 30 THEN 'C'
           WHEN i <= 36 THEN 'D'
           ELSE NULL
       END,
       CASE
           WHEN i <= 10 THEN 'C'
           WHEN i <= 24 THEN 'D'
           WHEN i <= 36 THEN 'C'
           ELSE NULL
       END,
       CASE WHEN i BETWEEN 21 AND 22 THEN 'N' WHEN i = 23 THEN 'UNKNOWN' ELSE 'R' END,
       'R',
       CASE
           WHEN i <= 10 THEN 15
           WHEN i <= 16 THEN 3
           WHEN i <= 18 THEN NULL
           WHEN i = 19 THEN 0
           WHEN i <= 24 THEN 12
           WHEN i <= 36 THEN 10
           ELSE NULL
       END,
       CASE
           WHEN i <= 10 THEN 15
           WHEN i <= 16 THEN 0
           WHEN i <= 18 THEN NULL
           WHEN i = 19 THEN 0
           WHEN i <= 22 THEN 12
           WHEN i <= 24 THEN 6
           WHEN i <= 36 THEN 5
           ELSE NULL
       END
FROM n;

INSERT INTO course_enrollment (student_id, cohort, course_id, grade)
SELECT CASE WHEN i < 10 THEN 's0' || i ELSE 's' || i END,
       '2022-23',
       1,
       CASE
           WHEN i <= 8 THEN '4'
           WHEN i <= 10 THEN '3.7'
           WHEN i = 11 THEN '2.0'
           WHEN i = 12 THEN '2'
           WHEN i = 13 THEN '3'
           WHEN i = 14 THEN '2.3'
           WHEN i = 15 THEN '1.0'
           WHEN i = 16 THEN '1.7'
           WHEN i = 17 THEN '1'
           WHEN i = 18 THEN '0.3'
           WHEN i <= 20 THEN 'F'
           WHEN i = 21 THEN 'W'
           WHEN i = 22 THEN 'I'
           WHEN i = 23 THEN 'A'
           ELSE 'P'
       END
FROM n
WHERE i <= 24;

INSERT INTO course_enrollment (student_id, cohort, course_id, grade) SELECT 's0' || i, '2022-23', 2, 'W' FROM n WHERE i <= 3;

INSERT INTO course_enrollment (student_id, cohort, course_id, grade) VALUES ('s01', '2022-23', NULL, NULL);

INSERT INTO course_enrollment (student_id, cohort, course_id, grade) SELECT 's' || i, '2024-25', 1, 'I' FROM n WHERE i >= 37;

-- Students 25-27 take four classes each. n is joined to itself to give each student the numbers 1 to 4.
INSERT INTO course_enrollment (student_id, cohort, course_id, grade)
SELECT 's' || a.i, '2023-24', b.i, 'P' FROM n AS a, n AS b WHERE a.i BETWEEN 25 AND 27 AND b.i <= 4;

INSERT INTO course VALUES (1, 'ENGL', '1302');
INSERT INTO course VALUES (2, 'MATH', '1314');
INSERT INTO course VALUES (3, 'BIOL', '1101');
INSERT INTO course VALUES (4, 'HIST', '1301');

-- The financial aid enrichment, for the unmet_need_band breakdown. An aid row names no term, so it
-- sits on its academic year's UNKNOWN term, the way the aid file loads. A student with no aid row
-- counts as UNKNOWN, which is why the bands still add up to everyone.
CREATE TABLE term (term_id INTEGER, academic_year TEXT, academic_term TEXT);
CREATE TABLE student_attribute (student_id TEXT, term_id INTEGER, attribute_key TEXT, attribute_value TEXT, source TEXT);

INSERT INTO term VALUES (901, '2022-23', 'UNKNOWN');
INSERT INTO term VALUES (902, '2023-24', 'UNKNOWN');
INSERT INTO term VALUES (903, '2024-25', 'UNKNOWN');
INSERT INTO term VALUES (911, '2022-23', 'FALL');
INSERT INTO term VALUES (912, '2023-24', 'FALL');
INSERT INTO term VALUES (913, '2024-25', 'FALL');
INSERT INTO term VALUES (921, '2022-23', 'SPRING');

-- Students 1 to 20 get a band, cycling through the four. The rest have no aid row.
INSERT INTO student_attribute
SELECT CASE WHEN i < 10 THEN 's0' || i ELSE 's' || i END,
       CASE WHEN i <= 24 THEN 901 WHEN i <= 36 THEN 902 ELSE 903 END,
       'unmet_need_band',
       CASE i % 4 WHEN 0 THEN '$0' WHEN 1 THEN '$1-2k' WHEN 2 THEN '$2-5k' ELSE '$5k+' END,
       'synthetic: test fixture'
FROM n WHERE i <= 20;

-- The synthetic affinity enrichment. It names no term, so it sits on the UNKNOWN term. 1-12 None, 13-16 Band,
-- 17-24 Student Government; 25-48 have no row, so they are UNKNOWN. Student 1 has a second row from another
-- source, which must not count them twice.
INSERT INTO student_attribute
SELECT CASE WHEN i < 10 THEN 's0' || i ELSE 's' || i END,
       901,
       'affinity',
       CASE WHEN i <= 12 THEN 'None' WHEN i <= 16 THEN 'Band' ELSE 'Student Government' END,
       'synthetic: test fixture'
FROM n WHERE i <= 24;
INSERT INTO student_attribute VALUES ('s01', 901, 'affinity', 'None', 'synthetic: second source');

-- Every class is in its cohort year's fall term, section 01. The row with no class has neither.
UPDATE course_enrollment
SET term_id = CASE cohort WHEN '2022-23' THEN 911 WHEN '2023-24' THEN 912 ELSE 913 END,
    section_id = '01'
WHERE course_id IS NOT NULL;

CREATE TABLE midterm_grade (student_id TEXT, term_id INTEGER, course_id INTEGER, section_id TEXT, midterm_grade TEXT);

INSERT INTO midterm_grade
SELECT CASE WHEN i < 10 THEN 's0' || i ELSE 's' || i END,
       911,
       1,
       '01',
       CASE
           WHEN i <= 8 THEN 'A'
           WHEN i <= 11 THEN 'B'
           WHEN i <= 14 THEN 'D'
           WHEN i <= 18 THEN 'L'
           WHEN i = 19 THEN 'D'
           WHEN i = 20 THEN 'L'
           WHEN i = 21 THEN 'W'
           WHEN i = 22 THEN 'D'
           ELSE 'L'
       END
FROM n WHERE i <= 24 AND i <> 23;

CREATE TABLE student_term_matrix (
    student_id TEXT, term_id INTEGER, retention_fall_to_spring TEXT, academic_standing TEXT, educational_goal TEXT
);

INSERT INTO student_term_matrix
SELECT CASE WHEN i < 10 THEN 's0' || i ELSE 's' || i END,
       911,
       CASE WHEN i <= 8 THEN 'still_enrolled' WHEN i <= 10 THEN 'not_returning' ELSE NULL END,
       CASE WHEN i <= 7 THEN 'good_standing' WHEN i <= 10 THEN 'not_in_good_standing' ELSE NULL END,
       CASE WHEN i <= 6 THEN 'graduate_and_transfer' ELSE 'no_declaration' END
FROM n WHERE i <= 12;

INSERT INTO student_term_matrix VALUES ('s13', 921, 'still_enrolled', 'good_standing', 'graduate_and_find_job');
INSERT INTO student_term_matrix VALUES ('s15', 912, 'still_enrolled', 'good_standing', 'graduate_and_find_job');
INSERT INTO student_term_matrix VALUES ('s01', 912, 'not_returning', 'not_in_good_standing', 'personal_enrichment');

INSERT INTO student_term_matrix
SELECT 's' || i,
       912,
       CASE WHEN i <= 34 THEN 'still_enrolled' ELSE 'not_returning' END,
       'good_standing',
       'take_classes_and_transfer'
FROM n WHERE i BETWEEN 25 AND 36;

INSERT INTO student_term_matrix SELECT 's' || i, 913, NULL, NULL, NULL FROM n WHERE i BETWEEN 37 AND 40;

-- Completion: the window is seen in full for 2022-23 only. Students 1-6 earn an associate in year 2,
-- 7-8 a certificate in year 3, 9 an associate too late (year 4), and 10 both (counted once): 9 of 24.
ALTER TABLE cohort_membership ADD COLUMN credit_years_observed INTEGER;
ALTER TABLE cohort_membership ADD COLUMN first_year_to_associates_at_coho INTEGER;
ALTER TABLE cohort_membership ADD COLUMN first_year_to_certificate_at_coh INTEGER;
UPDATE cohort_membership SET credit_years_observed = CASE cohort WHEN '2022-23' THEN 4 WHEN '2023-24' THEN 3 ELSE 2 END;
UPDATE cohort_membership SET first_year_to_associates_at_coho = 2 WHERE student_id IN ('s01', 's02', 's03', 's04', 's05', 's06');
UPDATE cohort_membership SET first_year_to_certificate_at_coh = 3 WHERE student_id IN ('s07', 's08');
UPDATE cohort_membership SET first_year_to_associates_at_coho = 4 WHERE student_id = 's09';
UPDATE cohort_membership SET first_year_to_associates_at_coho = 1, first_year_to_certificate_at_coh = 2 WHERE student_id = 's10';
