# Success measures

The shared shape for the core student success measures.
This folder holds the contract and the calculations for the measures.

The measures are retention, persistence, gateway completion (math and English, one measure each), DFW rate,
credit completion, fall-to-spring retention, good standing after the first fall, the midterm alert and
recovery rates, and completion. Fall-to-spring retention, good standing and the midterm rates read synthetic
enrichment tables; the midterm ones are **planted** (see below). Two more, `transfer_in_share` and
`part_time_share`, are cohort make-up rather than outcomes: who entered, out of every entering student.

A measure reads tables from the data model
and returns result rows. No files are read or written. Each institution runs this on its own data.

## A result row: `MeasureResult`

[models.py](models.py). One row per measure, cohort and group. Python 3.10 or newer, standard
library only. `measures/` is a Python package, so other code imports it with
`from measures.models import ...` and `from measures.run_measures import run_measure`.

| Field | Meaning |
| --- | --- |
| `measure` | A `Measure`: `retention`, `persistence`, `gateway_math`, `gateway_english`, `dfw_rate`, `credit_completion`, `fall_to_spring_retention`, `first_fall_good_standing`, `midterm_alert_rate`, `midterm_recovery_rate`, `completion`, `transfer_in_share` or `part_time_share` |
| `cohort` | A `Cohort`: one year, e.g. `2023-24`, or several pooled, e.g. `2021-22 + 2022-23` |
| `group` | A `Group`: which students the row is about. One condition or several. See below |
| `numerator`, `denominator`, `metric_rate` | The counts, and `numerator / denominator`. None if hidden. For `credit_completion` the numerator adds up student ratios, so it can have decimals |
| `status` | `ok`, `suppressed` (fewer than 10 students) or `not_yet_observable` (nobody in the cohort has an answer yet) |
| `suppressed` | A property, not a stored field: true whenever the status isn't `ok`, so the numbers are hidden |
| `n_excluded` | Students the measure applies to but we couldn't count (course enrollments for `dfw_rate` and the midterm measures) |
| `exclusions` | The same students (enrollments for `dfw_rate` and the midterm measures) split by reason: a count for each `ExclusionReason`, adding up to `n_excluded`. Retention and persistence have one reason (`unknown_outcome`), gateway has one (`unknown_requirement_or_outcome`), and DFW and credit completion can have several. Empty when nothing was left out or the row is hidden |
| `exclusion_reason` | The reason with the most students (or enrollments) left out, or none. For one reason it is that reason |
| `n_out_of_scope` | Students the measure doesn't apply to, such as students not required to take a gateway course. They are not in `n_excluded` |
| `note` | One sentence: who was counted and how |

## Groups

A `Group` is a set of conditions that all apply at once. Each condition is a `GroupDimension` (a
way to split students) and one of its values, e.g. `Group.of((PELL, "Y"))`.

- One condition is a simple group: `pell = Y`.
- Several make a combination: `Group.of((PELL, "Y"), (GENDER, "F"))` is Pell students who are female.
  Order doesn't matter, and a dimension can be used only once.
- No conditions is `EVERYONE`.

To ask for groups, pass `group_by` a list of `GroupBy`. `GroupBy.of(RACE)` gives the race groups, and
`GroupBy.of(PELL, ENROLLMENT_INTENSITY)` gives every Pell × intensity combination.

The values are the PDP dictionary's, plus `UNKNOWN`. A student whose value is blank, or isn't on the list,
counts in the `UNKNOWN` group, so the groups of one dimension always add up to everyone. A value
outside the list can't be built into a `Group`.

| Dimension | Values |
| --- | --- |
| `race` | the 8 PDP race values, e.g. `White`, `Two or More Races`, and `UNKNOWN` |
| `ethnicity` | `H`, `N`, `UNKNOWN` |
| `gender` | `M`, `F`, `P`, `X`, `UNKNOWN` |
| `first_gen` | `N`, `P`, `C`, `A`, `B`, `E`, `UNKNOWN` |
| `pell` | `Y`, `N`, `UNKNOWN` |
| `age_band` | `20 and younger`, `> 20-24`, `Older than 24`, `UNKNOWN` |
| `enrollment_type` | `First-time`, `Re-admit`, `Transfer-in`, `UNKNOWN` |
| `enrollment_intensity` | `Full-time`, `Part-time`, `UNKNOWN` |
| `cohort_term` | `Fall`, `Winter`, `Spring`, `Summer`, `UNKNOWN`: the term the student started in |
| `unmet_need_band` | `$0`, `$1-2k`, `$2-5k`, `$5k+`, `UNKNOWN`: the student's unmet need in their cohort year, from the financial aid enrichment. Bands, not dollars |
| `affinity` | `None` (no club or team, a value the file writes), `Band`, `Choir`, `Theater`, `Football`, `Baseball`, `Basketball`, `Volleyball`, `Soccer`, `Student Government`, `Esports`, `UNKNOWN`: from the synthetic affinity enrichment |
| `educational_goal` | the 8 student matrix goals, such as `graduate_and_transfer` or `no_declaration`, and `UNKNOWN`: the goal on the student's earliest matrix row. The generator draws one goal per student, so every row has the same one. A student with no matrix row (no courses in any fall term) is `UNKNOWN`, so that group's outcomes differ because of who has no fall term, not because of a goal |
| `course` | `dfw_rate` and `midterm_alert_rate` only (`COURSE_MEASURES`). The values come from the data: the course prefix and number, such as `ENGL 1302` |

Adding a breakdown means adding a dimension and its values in [models.py](models.py). A dimension the
measures' own query already selects needs nothing else. One that comes from an enrichment file, as
`unmet_need_band`, `affinity` and `educational_goal` do, also needs its join in
[calculations/sql_counts.py](calculations/sql_counts.py), listed in `ENRICHMENT_COLUMNS`: each wrapper
(`with_aid_band`, `with_affinity`, `with_educational_goal`) wraps the measure's query and is applied
only when a group asks for its dimension, so a measure that is never grouped by it needs neither the
join nor the table.

**Affinity and educational goal are noise.** Both are synthetic and independent of every outcome, except
`educational_goal = UNKNOWN`: those students have no matrix row (no fall term), so that group differs by
construction. Any other difference between their groups is noise, and every row grouped by either says so
in its `note` (`NOISE_NOTE` in `run_measures.py`). Their rates are published, but `publish.py` leaves them
out of the gap finder (`UNTESTED_DIMENSIONS`), so `equity_gaps` has no rows for them.

## Rules

A row that breaks these can't be built:

- A hidden group has None for counts, `metric_rate`, `n_excluded` and `n_out_of_scope`. Never 0, never a label like `<10`, so
  Excel, Power BI and pandas read the numbers as numbers.
- A shown group always has counts and a `metric_rate`.
- No two rows for the same measure, cohort and group (`check_unique`).

Hiding keeps a small group's own numbers off the row. Groups add up to a total, so if only one group
in a line were hidden, the total minus the shown groups would give it back. A line is a breakdown with
every dimension but one held fixed: a one-way breakdown adds up to everyone, and each row and column
of gender × race adds up to one gender or one race. `run_measure` stops that: while a line has exactly one
hidden group that anyone is counted in (`denominator` above 0), one more of its shown groups is hidden,
and that row's `note` says so. It avoids a group that is the only one counted in another line (it equals
that line's total), then takes the line's first covers (below), then a group whose other lines already
hide someone, then the smallest, and keeps checking until no line has one hidden group. A hidden group
nobody is counted in, such as an UNKNOWN group whose students are all out of scope, adds nothing to the
line's numerator and denominator, so it is no cover and needs none. The gap finder gets its rows from `run_measure`,
so `equity_gaps` follows the same rule.

A line whose total is everyone or a one-way group is always checked, because those totals are
published nearly everywhere (the gap finder saves one-way rows beside these). A line whose total has
two or more dimensions, such as course × race inside course × race × gender, is checked only when that
total is in the same run, and the total is then one of the line's groups, shown or hidden. If you
publish such a total, run it together with its breakdown. A total that holds a course, such as course ×
race, is the line's first cover, so running it beside its breakdown hides it rather than more of that
course's groups. A total across courses, such as race × gender, gets no such preference: pages read it
on its own.

A course's rows also add up across two dimensions at once. Its course × race and course × gender rows
share one course × race × gender group, so the course minus both rows plus that group is the sum of the
course's groups in neither that race nor that gender. No single line holds that sum, so each such
rectangle is a line too, adding up to the course row, with the course × race and course × gender rows
as its first covers. (On the mock data without these lines, BIO 130's 32 DFW enrollments minus its 21
White and 22 women's, plus its 12 White women's, gave back its one Asian man.) Without course × race
or course × gender in the run, a course's course × race × gender groups simply add up to the course row,
as one line. Both kinds need the course row shown: a hidden course is no known total.

A pooled cohort and its single years are one more line: the pool's group adds up to the same group in
each year. When a run holds a pool
and every one of its years, `run_measure` also hides single-year rows until no such line has exactly
one hidden group anyone is counted in, the pool's row included. It never hides a pooled row, so the pool
reads the same with or without its years. It prefers the same covers as above, then the smallest, and
checks the year's own lines again after each one, since hiding a single-year row can leave one of them
with one hidden group. If such a line has one hidden group and no single-year row left to hide (the
pool's row minus a year where nobody in the group is counted gives the other year's row exactly), that
group is treated as known, and its year's own lines are checked again as if it were shown, so it can't
give away a smaller group beside it. That row's `note` says it was hidden for the pooled cohorts. The single years
are run with every breakdown the pool has, so the run hides the pool's groups as before, and
`publish.py` keeps only the breakdowns approved for them. The manifest (`single_cohorts`) publishes
single years only for a few measures and one-way breakdowns, and only beside a pool that has all of its
years. On the mock data, one of the 384 published single-year group rows is hidden for its pool's line
(gateway math, 2023-24, Nonresident alien); 93 are hidden by the rules above.

It doesn't cover everything yet, so still treat hiding as display protection, not a guarantee:

- A group hidden as cover can be, in another line, the only group anyone is counted in. It then equals
  that line's total, so it covers nothing if that total is shown too. Covers are picked to avoid that,
  but nothing forbids it; on the mock data, none of the 1,856 published cover groups is one. A cover's own
  counts can also come out of a pooled cohort's line (above): that cover is then treated as known, but
  its counts are at least 10 students' and aren't hidden.
- Lines are checked one at a time, and the course lines above are the only ones across two dimensions.
  Other combinations of lines can narrow a hidden group to a range, and in rare patterns (a hidden group
  that links two blocks of hidden groups) to its exact count. The slow test solves every sum among the
  published rows together (`recoverable` in [tests/leaks.py](tests/leaks.py)). On the mock data it gives
  back nothing. The manifest publishes each measure and cohort in one run, so the solve takes a total
  outside the run as published nowhere. Taken as published, `dfw_rate`'s and `credit_completion`'s gender
  totals would give back gender X × Two or More Races (1 student, pooled): gender X holds only that
  student, so the row equals gender X, which is everyone minus the other genders. Publish such totals
  only in the measure's run, where hiding covers them (on the mock data that hides gender X and UNKNOWN
  and changes no other row).
- Only a pool and its own single years in the same run are checked against each other. Two pools that
  share years aren't (the manifest refuses them), nor is a run that holds a pool and only some of its
  years, such as `find_gaps` with `[["2022-23"], ["2021-22", "2022-23"]]`. Nor are a pool and a single
  year from different runs, such as a live page's single cohort beside the published pool. The
  Playground's live home state map, equity card and action board hide across their own lenses the
  same way. For a single pooled
  year, the executive view's headline tiles show a filter only when it's a published group, with no
  graduation tile, and the year-1 course load shows no matching curve. A 2024-25 tile has no arrow
  against a 2023-24 tile withheld that way. The home state map, supplemental rows and ID exports
  still show live filtered counts there.
- A single year's everyone row isn't in the pool's line, because hiding it would leave that year's groups
  with no total. A year with fewer than 10 students counted could then be worked out from the pool minus
  the other years, so publish single years only for years well above that.
- Cover protects the numerator and denominator only. `n_excluded`, `n_out_of_scope` and `exclusions`
  can be under 10 on a shown row, and subtraction can give a hidden group's. The query builder and MCP
  tools leave them out.
- Separate runs are never checked against each other. A group hidden in one measure's run can be
  shown in a related measure's run: a race × gender group hidden in `dfw_rate` can be shown in
  `midterm_alert_rate`, as one hidden in `retention` can be shown in `persistence`. The measures count
  different things, so this narrows a hidden group rather than giving its counts.
- Hiding a group's counts doesn't always hide its rate. When the hidden groups in a sum add up to a
  numerator of 0 (for `dfw_rate`, no D, F or W grades), each one's rate is pinned to 0%, though its
  counts stay hidden; when their numerator equals their denominator, each one's is pinned to 100%. On
  the mock data, version 6 pins 1,779 small `dfw_rate` groups and 1,155 `midterm_alert_rate` groups this
  way (650 and 368 in version 5): its course × race and course × gender rows add sums.

The counts are kept next to the `metric_rate` so
The gap finder can combine groups and compare a
group with everyone else.

## How each measure is calculated

Retention, persistence, the gateway measures and the two first-fall measures count students with a yes
or no answer. DFW rate and the two midterm measures count course enrollments. Credit completion averages
each student's ratio. The rate is `numerator / denominator`, rounded to 4 places.

| Measure | Counts as achieved | Counted in the denominator | Left out |
| --- | --- | --- | --- |
| `retention` | `retention` is true | `retention` is true or false | blank answer: `n_excluded`, reason `unknown_outcome` |
| `persistence` | `persistence` is true | `persistence` is true or false | blank answer: `n_excluded`, reason `unknown_outcome` |
| `gateway_math`, `gateway_english` | the year 1 completed flag is `C` | the flag is `C` or `D` | not required (status `N`): `n_out_of_scope`, outside the measure. Requirement or outcome unknown: `n_excluded`, reason `unknown_requirement_or_outcome` |
| `dfw_rate` | the grade is a D, F or withdrawal | the grade is one we can classify (see below) | any other grade: `n_excluded`, with the reason in the grade table below |
| `fall_to_spring_retention` | the first fall matrix row says `still_enrolled` | fall starters with a first fall row and an answer | blank answer: `unknown_outcome`. Other starters, and fall starters with no row for that fall: `n_out_of_scope` |
| `first_fall_good_standing` | the first fall matrix row says `good_standing` | fall starters with a first fall row and a standing | blank standing: `no_graded_credits`. Other starters, and fall starters with no row for that fall: `n_out_of_scope` |
| `midterm_alert_rate` | the midterm grade is `D` or `L` (failing) | enrollments with a midterm grade of `A`, `B`, `C`, `D` or `L` | no midterm grade: `no_midterm_grade`. Another code: `unlisted_grade`. A midterm `W` (withdrew before midterm): `n_out_of_scope` |
| `midterm_recovery_rate` | the final grade is not a D, F or withdrawal | enrollments alerted at midterm (`D` or `L`) with a final grade we can classify, as for `dfw_rate` | a final grade we can't classify: the DFW grade reasons |
| `credit_completion` | the student's own ratio, credits earned / credits attempted in year 1 (added up) | first-time and transfer-in students with at least 1 credit attempted and a known full- or part-time status | no credits recorded: `unknown_outcome`. Under 1 attempted: `no_credits_attempted`. Enrollment type unknown: `unknown_enrollment_type`. Full- or part-time unknown: `unknown_attendance_type`. Re-admit and continuing students: `n_out_of_scope` |
| `completion` | an associate or certificate earned here in years 1 to 3 (counted once) | every student in a cohort the data has seen for 3 full years (`credit_years_observed` minus the year in progress) | a cohort short of the window: `not_yet_observable`, and so is a pool holding one |
| `transfer_in_share` | enrollment type transfer-in | every entering student, so the denominator is the cohort's headcount | none |
| `part_time_share` | first-term enrollment intensity part-time | every entering student, so the denominator is the cohort's headcount | none |

- **Hidden groups:** fewer than 10 students counted in the denominator (for `dfw_rate`, fewer than 10
  students with a graded enrollment). A cohort has status
  `not_yet_observable` if nobody in it has an answer yet. A pooled cohort has it when any of its years
  has no answers yet.
- **Group values** are matched ignoring case and spaces, because the data model keeps the source file's
  spelling.

**Retention** means enrolled again in the next academic year, or earned a credential by then. A student who started in Fall 2023 and one who started in Spring 2024 are both in the 2023-24 cohort, and both are checked against 2024-25. The fall starter has about a year to return, and the spring starter has about five months. The group's rate is a blend, so spring starters tend to pull it down. Add `cohort_term` to `group_by` to compare them.

**Persistence** means the student was enrolled at another institution, or earned a credential there,
by their second academic year. A student can be both retained and persisted, so the two can't be added
together to get "enrolled anywhere".

**Gateway completion** (`gateway_math` and `gateway_english`) means a student required to take gateway math
or English got a grade of 1.0 or higher, or a pass, in it during their first academic year. It counts every
student who was required to take the course, so it is the same as the Postsecondary Data Partnership's
first-year gateway course completion: students who completed a required gateway course, out of all students
required to take one. The cohort file stores it as a completed flag: `C` for completed, `D` for did not
complete, `NA` for not required. It also stores whether the course is required: `R` required, `N` not required,
`UNKNOWN` or blank if nobody knows.

Students who aren't required to take the course are outside the measure. They are counted in `n_out_of_scope`,
not in `n_excluded`, so they don't look like a data problem. A student whose requirement is unknown, or who is
required but has no outcome, can't be classified. They are in `n_excluded`, with the reason
`unknown_requirement_or_outcome`.

A required student who never took the course in year 1 is a `D`, so they count as not completed. For example,
take 10 students: 4 required, took it and passed (`C`); 2 required, took it and did not pass (`D`); 2
required and never took it (`D`); 2 not required. The rate is 4 of 8, or 50%. The two who weren't required are
outside the measure (`n_out_of_scope` is 2).

**Unknown attempts.** In the mock data almost every required student whose attempt is unknown is coded `D`, so
they count as not completed. They are a large share of the denominator, and the rate is much higher without
them. This follows the PDP definition, so they stay in. Finding `N1` in `data/quality/findings.csv` has the counts.

**No required students.** If an institution doesn't report whether students are required to take the course,
nobody has a `C` or `D`, and the measure shows `not_yet_observable`, which reads as "too new". Check the
requirement flags in the data before reading it that way.

**DFW rate** is the share of course enrollments, with a final grade, that ended in a D, F or withdrawal.
Each enrollment is counted in the cohort and the groups of the student who took it, across all their terms.
Rows with no class (a term spent at another college) aren't enrollments and aren't counted at all. For this
measure the counts, `n_excluded` and the numerator are course enrollments, not students. Hiding still goes
by distinct students.

The course file has no letter grades. `Grade` is text: a number from 0 to 4 (grade points), or a code. In the
dictionary the code `A` means audit, not an A. So a D or F is inferred from the number: any grade under 2.0.
A withdrawal is its own code, `W`, and counts as a DFW.

| Grade in the course file | Counted as | Reason it is left out |
| --- | --- | --- |
| A number from 0 to 4 (written `1` or `1.0`) below 2.0 | D or F: in the numerator and the denominator | |
| A number from 2.0 to 4.0 | passed: in the denominator only | |
| `F` or `W` | D or F: in the numerator and the denominator | |
| `P` | passed: in the denominator only | |
| `I` (incomplete) | left out | `incomplete` |
| `A` (audit) | left out | `audit` |
| `MIS` (missing) | left out | `missing_grade` |
| `O` or `OTH` (other) | left out | `other_grade` |
| `UNKNOWN` (the loader also turns `M` and `UK` into `UNKNOWN`) | left out | `unknown_grade` |
| Codes the dictionary doesn't list (`UW`, `N`, `CHE`, ...) or no grade | left out until their meaning is confirmed | `unlisted_grade` |

Grades match ignoring case and spaces, and a number can have up to two decimals (`3.67`, `4.00`, `w`).

**Open question: the cutoff.** A grade under 2.0 is a D or F (below a C), so a 1.7 (C minus) counts as a
DFW. If the cutoff were 1.7 instead, a C minus would count as a pass and the rates would be lower. The cutoff is
one setting, `DFW_BELOW`, in [calculations/dfw.py](calculations/dfw.py). Until that is settled, it is 2.0.

**DFW by course.** `GroupBy.of(COURSE)` gives one group for every course with an enrollment in the requested
cohorts, so the courses come from the data, not a fixed list. A course is its prefix and number, such as
`ENGL 1302`, and it only applies to `dfw_rate` and `midterm_alert_rate`: asking another measure for it is an error. It can be combined
with other groups, like `GroupBy.of(COURSE, PELL)`. Most courses have fewer than 10 students and are hidden, so a
run returns many rows with the status `suppressed`. Courses that differ only in case, like `ENG 101` and `eng 101`, are one course. A college that gives different
classes the same code will see them as one course.

**Credit completion** is how much of the credit load students attempted in their first academic year they
earned. It is modeled on the Postsecondary Data Partnership's (PDP) credit completion ratio, as described on
NSC's [First Year Credit Completion Ratio](https://help.studentclearinghouse.org/pdp/knowledge-base/first-year-credit-completion-ratio-benchmarking-dashboard/)
and [Credit Momentum](https://help.studentclearinghouse.org/pdp/knowledge-base/credit-momentum-dashboard/)
dashboard pages. It is not PDP's exact calculation:

- A student's ratio is credits earned / credits attempted in year 1 (`number_of_credits_earned_yr_1` and
  `number_of_credits_attempted_yr_1`). The group's figure is the **average of the students' ratios**, not
  total credits earned over total credits attempted. A student who attempted 3 credits counts as much as one
  who attempted 15. In a row, `denominator` is the number of students counted, `numerator` is the sum of
  their ratios, and `metric_rate` is the average.
- Who is counted: first-time and transfer-in students who attempted at least one credit (1 or more).
  Re-admit and continuing students are outside the measure (`n_out_of_scope`). A blank or unknown enrollment
  type is left out (`unknown_enrollment_type`).
- **Unknown full- or part-time status is left out** (`unknown_attendance_type`), as the Credit Momentum page
  and the Subgroup Gap Analysis page say. The First Year page includes those students. In the mock data it
  moves the rate by at most 0.0005.
- A ratio above 1 (more credits earned than attempted) is counted as 1, and nothing flags it. The data model
  checks earned against attempted in the course rows but not in these year 1 totals. The mock data has no such
  rows.
- What counts as an earned credit is whatever the data's earned column says. We sum it as given.
- PDP starts each student's year from their starting term, summer and intersession included. The data model
  only has the year 1 totals, so the measure uses those as given.

**Fall-to-spring retention and good standing after the first fall** read the student matrix
(`student_term_matrix`), which has one row per student per fall. Both count fall starters only, one yes or
no per student per cohort, from their row for the fall of their cohort year: the first fall. Spring, summer
and winter starters, and fall starters with no row for that fall, are outside the measure
(`n_out_of_scope`). Retention to spring is `still_enrolled` or `not_returning`. Good standing means a
cumulative GPA of 2.0 or more after that fall; a blank standing means no graded credits, and those students
are left out (`no_graded_credits`, about 18% of fall starters in the mock data). The matrix is synthetic,
derived from the mock course file.

**Midterm alert and recovery rates** read the synthetic midterm grades (`midterm_grade`): `A`, `B`, `C`,
`D`, `L` (failing) or `W` (withdrew before midterm). There is no midterm F. An enrollment matches its
midterm grade on student, term, course and section, and the join drops nothing from the enrollments that
DFW counts. The alert rate is the share of enrollments with a midterm grade other than `W` that got a `D` or
`L`. The recovery rate is the share of those alerted enrollments, with a final grade, that did not end in a
D, F or withdrawal, using DFW's grade rules. Like DFW, both count enrollments, and hiding goes by distinct
students. The alert rate can be broken down by course; the recovery rate can't.

**PLANTED.** The synthetic midterm grades are generated from the final grades, so any link between a midterm
alert and a D, F or withdrawal is circular by construction. These two measures only show that the pipeline
works, and their `note` says so wherever it is shown. There is no intervention data either, so "recovery"
says nothing about whether alerts work. Navigate alerts will replace them once real fields arrive.

### Known issues in the mock data

The mock data has known bugs that affect some groups and measures. They are listed, with counts and
proposed fixes, in `data/quality/findings.csv`:

- **Retention and persistence:** rows `3` and `N15`.
- **Groups** (first gen, Pell, enrollment values): rows `1`, `7a` and `N6`.
- **DFW rate:** row `9`, duplicate class rows. They count more than once.
- **Credit completion:** row `4`, year 1 credits attempted that differ from the student's course rows (1,303 students), and row `N20`, credits attempted below the minimum of 1. Those students are left out (`no_credits_attempted`).

## Running a measure

[run_measures.py](run_measures.py) is the entry point: `run_measure(measure, cohorts, group_by)`
returns a row for every cohort and group (everyone, plus every group asked for in `group_by`). It
reads from the loader's SQLite file (`normalized-data-model/output/pdp.sqlite`). Pass `database` to
read another SQLite file by path, or an open connection (for PostgreSQL). A measure that isn't written yet raises `NotImplementedError`.

Each measure's calculation is its own file in [calculations/](calculations/): `retention.py`,
`persistence.py`, the two gateway files, `dfw.py`, `credit_completion.py`, `fall_to_spring_retention.py`,
`first_fall_good_standing.py`, `midterm_alert.py` and `midterm_recovery.py`. `students.py` and `midterm.py`
hold the queries those files share. A measure file has two parts, and `run_measures.py` does the rest (building the
groups, hiding groups under 10 students, working out the rate):

- `NOTE`: the sentence that says who was counted
- `count(connection, cohorts, groups)`: return a `Counts` (numerator, denominator and the students
  counted) for every `(cohort, group)`

A measure can count in SQL or in Python, as long as it returns that. Retention and persistence count in
SQL: each gives one query that returns a row per student per cohort (the group columns, whether the
student has an answer, and whether they achieved it), and
[sql_counts.py](calculations/sql_counts.py) does the grouping in the database, one `GROUP BY` for each kind
of group, with `SUM(...)` over each student's 1, 0 or ratio. Group values match ignoring case and spaces, inside
the database (`UPPER(REPLACE(col, ' ', ''))`), because the data stores `FALL` and `>20 - 24`. A pooled
`Cohort` is counted together in the query. A blank or unlisted group value counts as `UNKNOWN`. The SQL is plain, with no query placeholders, so it runs on
SQLite and PostgreSQL. A measure with branching rules, such as D/F/W grades, can count in Python instead.

To add a measure, write its file and list it in `MEASURES` in `run_measures.py`.

**Saving results:** `run_measure(..., save=True)` also writes the rows to
`measures/output/success_measures.sqlite`, in one table, `success_measures`, for all measures. It is its
own file, not the loader's, so a reload of the data doesn't touch it. It holds only counts and rates
(small groups hidden), so it can be shared without any student rows. Each row has the `data_loaded_at`
of the data it came from. The `output/` folder is gitignored.

A results file saved before `exclusions` existed gets the new column when you save to it.

A save is always the latest run. It removes the rows saved earlier for the same measure and cohort,
then writes the new ones. For example:

```python
# 1. Saves retention for 2022-23: everyone, every Pell group and every race group.
run_measure(Measure.RETENTION, [Cohort.of("2022-23")],
            [GroupBy.of(GroupDimension.PELL), GroupBy.of(GroupDimension.RACE)], save=True)

# 2. Saves retention for 2022-23 again, only for everyone. The Pell and race rows from 1 are gone.
run_measure(Measure.RETENTION, [Cohort.of("2022-23")], save=True)

# 3. Saves persistence. The retention rows from 2 stay.
run_measure(Measure.PERSISTENCE, [Cohort.of("2022-23")], save=True)
```

So to keep several breakdowns together, ask for them all in one call, as in 1. After the data is
reloaded, run again to refresh the saved rows.

**Publishing the approved results:** [manifest.yaml](manifest.yaml) lists the measure, cohort and
breakdown combinations approved for publication. From the repo root, after loading the data:

```bash
python -m measures.publish
```

It runs each measure and cohort once, with every breakdown the manifest lists for it, and the gap
finder compares the groups of that same run. One run hides one set of groups, so rows from different
runs can't be set against each other, and `success_measures` and `equity_gaps` hide the same groups.
Within the run, hiding has the limits listed under [Rules](#rules): display protection, not a
guarantee. It writes
a fresh `success_measures.sqlite` (nothing older is kept) and `success_measures.publication.json`
beside it, with the manifest's version and both files' SHA-256. The query builder
([mcp/pdp_mcp/results.py](../mcp/pdp_mcp/results.py)) answers only from a file that matches that
record, and only what the manifest approves. To publish something new, add it to the manifest, raise
its version, and publish again. No year can be in two cohorts. A measure listed under `single_cohorts`
is run once for its pool and every single year together, so hiding checks the pool against its years
(see [Rules](#rules)), and only the single years' approved breakdowns are kept for them.

Version 7 publishes what the student success and enrollment trends tiles show, so the chat can
check every tile: `completion` (pooled and single years), `fall_to_spring_retention`'s single years, and the
make-up measures `transfer_in_share` and `part_time_share` by race, gender and Pell, pooled and single
years. The make-up measures get no `equity_gaps` rows (`NO_GAPS` in `publish.py`): a group "behind" on who
entered is no shortfall. Completion's 2023-24 and 2024-25, and so its pool, are `not_yet_observable`. A pool
with no answers yet publishes no numbers, so hiding no longer checks it against its years: before, it hid one
year's row in every completion group to cover a pool row that has nothing to subtract from. Every version 6
row is the same.

Version 7 also writes a `measure_trends` table: for each measure with single cohorts, each group's change
from the previous single year, read by `compare()` and worded by `Change.label` (see [Trends](#trends-comparepy)).
A row is written only when both years' rows are shown, never for a pool, and never for a year that
`single_cohorts: no_trend` lists for the measure (retention and persistence in 2024-25, which hasn't had all
of year 2, so its change would read as a drop). `kpi = entering_students` holds the change in the make-up
measures' everyone denominator. The table is in the results file, so the publication record's checksum
covers it, and `query_results` returns it with `include: ["rates", "trends"]`.

Version 6 approves course × race and course × gender for `dfw_rate` and `midterm_alert_rate`, and
race and gender (one-way) for `midterm_alert_rate` and `midterm_recovery_rate`, for the course outcomes
page's All races and All genders choices. Each runs with its measure's other breakdowns, so a course ×
race or course × gender row is the total of its course × race × gender line (see [Rules](#rules)). On
the mock data, every version 5 row is the same except 11 course × race × gender rows (10 to 14
enrollments each, in six small courses), now hidden, and `equity_gaps` is unchanged: these measures
count more than yes or no, so they add no gaps. Version 5 gave away 5 small groups in `dfw_rate` and 4
in `midterm_alert_rate` when a course row was combined with its course × race × gender rows, such as
BIOG 221's White men. Nine of the 11 rows cover those, and version 5's breakdowns run alone now hide the
same 9.

Version 5 publishes the 2021-22 to 2024-25 single cohorts for retention, persistence, gateway math and
gateway English, by race, gender, Pell, age band and enrollment intensity, for the executive view. Every
pooled row is the same as in version 4. 2024-25 is outside the pool, so nothing it publishes can be
subtracted from it.

Version 4 approves `pell` and `unmet_need_band` (one-way) for `dfw_rate` and `credit_completion`, so the
aid momentum page can read them from the published file instead of running the measures live. Both measures
count more than yes or no, so they add rates but no `equity_gaps` rows. The bands come from the synthetic
financial aid file, whose link with retention is planted. Home state is not in the manifest.

**Logging:** `run_measure` logs one summary line per run (rows shown and hidden, and when the data was
loaded) and warns when a cohort has no answers yet or every row is hidden. It uses Python's standard
`logging`, so turn it on with `logging.basicConfig(level=logging.INFO)`. At `DEBUG` it also logs each
loaded data file and its SHA-256, so a number can be traced to the files it came from.

```python
run_measure(
    measure=Measure.RETENTION,
    cohorts=[Cohort.of("2022-23")],
    group_by=[GroupBy.of(ENROLLMENT_TYPE)],
)
```

`cohorts` and `group_by` take objects from [models.py](models.py), checked when they are built: a
`Cohort` needs at least one year and no repeats, and a `GroupBy` needs at least one dimension and no
repeats.

**Pooling cohorts:** a `Cohort` with several years, like `Cohort.of("2021-22", "2022-23")`, counts
those cohorts together. They are pooled before small groups are hidden, so a group under 10 in each
cohort can reach 10 together and be shown.

## Tests

[tests/test_measures.py](tests/test_measures.py) checks the calculations on a tiny made-up database,
[tests/fixture.sql](tests/fixture.sql): 48 students, with the expected numbers worked out by hand in
that file's header. It needs no loader. [tests/test_measures_postgres.py](tests/test_measures_postgres.py)
runs the same fixture on PostgreSQL when `PDP_TEST_POSTGRES_URL` is set (CI sets it). `make check` runs it, or run it alone from the repo root:

```bash
python -m pytest measures/tests
```

## Sample

[samples/samples.py](samples/samples.py) shows six examples: what you pass to `run_measure` and the rows
that come back. By default the rows are made up and no database is read. The data is mock, so the numbers
mean nothing either way. To run them on the loaded database, load the data first, then run it from the
repo root:

```bash
cd normalized-data-model
python -m src.loader.load
cd ..
python measures/samples/samples.py
```

Add `--input path/to/pdp.sqlite` to run on a loaded database instead of showing made-up rows. Add
`--save` to also save the rows shown and print what was saved. Real rows go to
`success_measures.sqlite`. Made-up rows go to `success_measures_sample.sqlite`, so they can't replace
real results.

- **Sample 1:** retention for one cohort, grouped by enrollment type and by Pell × intensity.
- **Sample 2:** retention for two pooled cohorts, grouped by enrollment type.
- **Samples 3 and 4:** gateway math and gateway English for one cohort, grouped by Pell status. They are the
  same call with a different `measure`.
- **Sample 5:** DFW rate for one cohort, grouped by Pell status. Its counts are course enrollments.
- **Sample 6:** DFW rate for one cohort, grouped by course. A real run returns a row for every course, so
  only the first 15 rows are printed.
- **Sample 7:** credit completion for one cohort, grouped by Pell status. The numerator has decimals, because it adds up student ratios.

## Trends: `compare.py`

[compare.py](compare.py) is how every KPI trend arrow reads a change from one cohort to the next, so
everyone judges a change the same way.

- `compare(earlier, latest)` takes two `MeasureResult` rows of one measure and returns a `Change`, or
  None when either row is hidden or not yet observable.
- `compare_values(name, earlier, latest)` does the same for plain numbers, such as a headcount.
- A `Change` has `relative_pct` ((latest - earlier) / earlier * 100), `direction` (`up`, `down`,
  `flat`) and `judgement` (`good`, `bad`, `neutral`).
- A change under `SAME_WITHIN_PCT` (1%) is `flat`. `TREND_RULES` says which way is better for each KPI;
  add a row there for a new one.
- `Change.label(previous)` is the arrow's wording, such as `−3.5% vs 2022-23`. The Playground tiles and the
  published `measure_trends` both use it, and both compare the rates as published (rounded to 4 places), so a
  tile's arrow and the chat's `trend_label` agree even at the edge of the 1% band.
