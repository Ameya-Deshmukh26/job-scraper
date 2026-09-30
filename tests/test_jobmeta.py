"""Job type, workplace, pay and relative ages, normalised across sources."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jobmeta  # noqa: E402


@pytest.mark.parametrize("raw, title, expected", [
    ("FullTime", "", "Full-time"),            # Ashby
    ("Full time", "", "Full-time"),           # Workday
    ("full-time", "", "Full-time"),           # Amazon
    ("Contractor", "", "Contract"),           # Google Jobs
    ("Intern", "", "Internship"),             # Lever commitment
    ("PartTime", "", "Part-time"),
    ("", "Machine Learning Engineer Intern", "Internship"),
    ("", "Data Analyst (Contract)", "Contract"),
    ("", "Data Engineer - W2 only", "Contract"),
    ("", "Data Scientist", ""),               # nothing to go on
    ("Full-time", "Summer Intern", "Full-time"),   # the source's own value wins
])
def test_job_type(raw, title, expected):
    assert jobmeta.job_type(raw, title) == expected


@pytest.mark.parametrize("raw, title, location, expected", [
    ("Hybrid", "", "", "Hybrid"),
    ("remote", "", "", "Remote"),
    ("", "Data Scientist (Remote)", "", "Remote"),
    ("", "Data Analyst", "Remote, US", "Remote"),
    ("", "Data Analyst", "Austin, TX", ""),
    ("", "", "Work from home", "Remote"),
    ("On-site", "", "", "On-site"),
])
def test_workplace(raw, title, location, expected):
    assert jobmeta.workplace(raw, title, location) == expected


@pytest.mark.parametrize("text, pay", [
    ("Senior Engineer | Remote | $120k-$150k | Full-time", "$120k-$150k"),
    ("Pay: $45/hr on W2", "$45/hr"),
    ("€75k–110k plus equity", "€75k–110k"),
    ("No salary listed here", ""),
])
def test_pay_from_text(text, pay):
    assert jobmeta.pay_from_text(text) == pay


@pytest.mark.parametrize("text, delta", [
    ("5 hours ago", timedelta(hours=5)), ("30 minutes ago", timedelta(minutes=30)),
    ("2 days ago", timedelta(days=2)), ("Just now", timedelta(0)), ("1 week ago", timedelta(weeks=1)),
])
def test_relative_ages(text, delta):
    got = datetime.now(timezone.utc) - jobmeta.age_to_datetime(text)
    assert abs(got - delta) < timedelta(seconds=5)


def test_unreadable_age_is_none():
    assert jobmeta.age_to_datetime("Promoted") is None


def test_labelled_lines_give_type_and_workplace():
    text = "About the role...\nSeniority level: Entry level\nEmployment type: Contract\nWorkplace type: Hybrid"
    assert jobmeta.labels_from_text(text) == ("Contract", "Hybrid")


def test_free_text_is_not_read_as_a_label():
    assert jobmeta.labels_from_text("You will manage contract negotiations remotely.") == ("", "")
