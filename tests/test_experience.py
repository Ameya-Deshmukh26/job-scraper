"""
Years-of-experience requirement. The rule: any number next to "years" is a
requirement, and a job asking for more than 3 is dropped. These pin down
what counts, and the look-alikes that must not.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experience import html_to_text, required_years, too_senior  # noqa: E402


@pytest.mark.parametrize("text, years", [
    # plain requirements, any phrasing
    ("5+ years of experience in data science", 5),
    ("3+ years of Python", 3),
    ("4 years experience with SQL", 4),
    ("Minimum of 6 years of relevant experience", 6),
    ("At least 4 yrs working with Spark", 4),
    ("4 or more years in analytics", 4),
    ("five (5) years of professional experience", 5),
    ("Ten+ years building ML systems", 10),
    ("2 years of hands-on experience", 2),
    ("Requires 10+ years' experience", 10),
    # ranges: the lower bound is what is required
    ("2-5 years of experience", 2),
    ("3 to 5 years of experience", 3),
    ("4–6 years of experience", 4),
    ("3-5+ years in a data role", 3),
    # several requirements: the highest applies
    ("3+ years of SQL and 5+ years of Python", 5),
    ("Experience:\n• 2+ years with dashboards\n• 4+ years with statistics", 4),
    # alternative paths: the easiest one applies
    ("Bachelor's degree and 5 years of experience, or Master's degree and 3 years of experience", 3),
    ("5 years of experience with a BS, or 2 years with an MS", 2),
])
def test_requirements_are_counted(text, years):
    assert required_years(text)[0] == years


@pytest.mark.parametrize("text", [
    "Bachelor's degree from a 4-year university",
    "a 4 year degree in computer science",
    "Founded 25 years ago, we are a leader in analytics",
    "Equity vests over 4 years",
    "We have grown every year for the past 10 years",
    "Up to 3 years of experience",
    "Less than 5 years of experience welcome",
    "5+ years of experience preferred",
    "Nice to have: 6+ years in fintech",
    "Ideally 5 years of experience with Kafka",
    "Our customers range from 5 to 90 years old",
])
def test_things_that_are_not_requirements_are_ignored(text):
    assert required_years(text)[0] is None, required_years(text)


def test_a_preferred_section_does_not_count_but_the_required_one_does():
    jd = """Minimum Qualifications
    • 2+ years of experience in data analysis
    Preferred Qualifications
    • 6+ years of experience in machine learning
    • PhD in a quantitative field"""
    assert required_years(jd)[0] == 2


def test_a_bonus_bullet_does_not_hide_the_bullets_after_it():
    """A short bullet mentioning "bonus" is not a section heading."""
    jd = "Requirements:\n• Bonus if you know Go\n• 5+ years of backend experience"
    assert required_years(jd)[0] == 5


def test_a_degree_mention_in_the_same_sentence_does_not_hide_the_requirement():
    assert required_years("A 4-year degree and 3+ years of experience")[0] == 3


def test_the_evidence_sentence_is_returned():
    need, why = required_years("About us.\nYou have 7+ years of experience shipping models.")
    assert need == 7 and "7+ years" in why


@pytest.mark.parametrize("text, dropped", [
    ("3+ years of experience", False),       # 3 is fine
    ("4+ years of experience", True),        # above 3
    ("3-5 years of experience", False),      # lower bound 3
    ("4-6 years of experience", True),
    ("no years mentioned at all", False),
])
def test_the_above_three_rule(text, dropped):
    assert bool(too_senior(text, 4)) is dropped


def test_html_is_turned_into_lines():
    raw = "&lt;ul&gt;&lt;li&gt;5+ years of SQL&lt;/li&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"   # Greenhouse escapes it
    text = html_to_text(raw)
    assert "5+ years of SQL" in text and "\n" in text
    assert required_years(text)[0] == 5


# ── one path per degree: the candidate's own degree decides ───────────────

@pytest.mark.parametrize("text, degree, years", [
    ("Bachelors + 8 years or Masters + 6 years or Phd + 3 years", "masters", 6),
    ("Bachelors + 8 years or Masters + 6 years or Phd + 3 years", "bachelors", 8),
    ("Bachelors + 8 years or Masters + 6 years or Phd + 3 years", "phd", 3),
    ("Master's degree in a quantitative field, or Bachelor's degree and 5+ years of experience", "masters", 0),
    ("Master's degree in a quantitative field, or Bachelor's degree and 5+ years of experience", "bachelors", 5),
    ("PhD with 1-3 years, MS or MA with 2-6 years, or BS or BA with 4-8 years of experience", "masters", 2),
    ("PhD with 1-3 years, MS or MA with 2-6 years, or BS or BA with 4-8 years of experience", "bachelors", 4),
    ("5 years of experience with a BS, or 2 years with an MS", "masters", 2),
    ("5 years of experience with a BS, or 2 years with an MS", "bachelors", 5),
    # one degree only: not a choice of paths, the years just apply
    ("Master's degree or equivalent experience, and 5+ years of experience", "masters", 5),
    ("BS in Computer Science or a related field and 4+ years of experience", "masters", 4),
])
def test_degree_paths(text, degree, years):
    assert required_years(text, degree)[0] == years


@pytest.mark.parametrize("text", [
    "For over 30 years, Citadel has cultivated a culture of learning",
    "For more than 20 years we have served our customers",
    "Our founders bring 40 years of combined experience",
])
def test_company_history_is_not_a_requirement(text):
    assert required_years(text)[0] is None
