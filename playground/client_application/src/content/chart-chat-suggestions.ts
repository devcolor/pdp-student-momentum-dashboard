/**
 * The questions each chart card's "Ask" button offers, keyed by the card's id. Only cards listed here get the
 * button. Each question is answerable from a published breakdown or a definition, and several are worded to
 * match a breakdown another page draws, so the answer comes back with a link to that page.
 *
 * Keys are ChartCard ids: exec-* in executive-view (charts.tsx, home-state-map.tsx, course-load.tsx),
 * deaggregation-outcomes, course-dfw, course-midterms, aid-* in aid-momentum/charts.tsx, and success-* in
 * student-success (equity.tsx, actions.tsx). The chart card story checks every key is one of these.
 */
export const chartChatSuggestions: Record<string, readonly string[]> = {
  "exec-equity-gaps": [
    "How does retention differ by race and gender, and which of those gaps could be noise?",
    "How does retention differ by age group?",
    "How does retention change across unmet need bands, and what should I know about that pattern?",
  ],
  "exec-headcount": [
    "How is headcount by term counted on this chart, and which fields does it use?",
    "How does persistence differ by race?",
    "Which breakdowns of this data are published?",
  ],
  "exec-home-state": [
    "Which fields hold a student's home state, and is home state a published breakdown?",
    "Which breakdowns of this data are published?",
    "How is headcount counted on this chart?",
  ],
  "exec-course-load": [
    "How does retention compare for full-time and part-time students?",
    "Which courses have the highest DFW rates?",
    "How is course load defined on this chart?",
  ],
  "deaggregation-outcomes": [
    "Which measure shows this group's largest gap?",
    "How does this group's retention compare with the other gender of the same race?",
    "Are any numbers for this group hidden because the group is small?",
  ],
  "course-dfw": [
    "Which courses have the highest DFW rates for this group?",
    "How does this group's DFW rate compare across these courses?",
    "How is the DFW rate defined?",
  ],
  "course-midterms": [
    "What does the midterm alert rate measure, and why is it planted?",
    "How do midterm alert rates differ by course?",
    "How is a student who recovers after a midterm alert counted?",
  ],
  "aid-by-band": [
    "How does this measure change across unmet need bands, and why is that link planted?",
    "How does retention compare for Pell and non-Pell students?",
    "How does credit completion differ by Pell status?",
  ],
  "aid-gaps": [
    "How does this measure change across unmet need bands, and why is that link planted?",
    "How does retention compare for Pell and non-Pell students?",
    "How does credit completion differ by Pell status?",
  ],
  "aid-pell": [
    "How does retention compare for Pell and non-Pell students?",
    "How does credit completion differ by Pell status?",
    "How does this measure change across unmet need bands, and why is that link planted?",
  ],
  "success-equity": [
    "How does retention differ by age group?",
    "How does retention differ by gender?",
    "How does retention differ by Pell status?",
  ],
  "success-actions": [
    "Which courses have the highest DFW rates?",
    "How do gateway math outcomes differ by race?",
    "How does year-one credit completion differ by race?",
  ],
};
