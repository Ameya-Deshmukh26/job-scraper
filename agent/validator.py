"""
Deterministic fabrication validator — zero LLM calls.

Tailoring is allowed to *reframe* Ameya's history toward a JD. It is not
allowed to invent it. This module turns that rule into a mechanical check:

  1. provenance   every tailored bullet must trace to a corpus item
                  above a similarity floor
  2. metric lock  every number in a tailored bullet must already exist
                  somewhere in the corpus
  3. skill floor  every technology named must appear in the base resume

Every report records the thresholds it ran with, so a run is reproducible
and an audit trail is possible.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from .corpus import BASE_TEX, CorpusItem, corpus_numbers, numbers_in, strip_tex

# Tunable thresholds — recorded in every report
PROVENANCE_FLOOR = 0.34   # SequenceMatcher ratio against best corpus item
STRICT_METRICS   = True   # invented numbers are errors, not warnings

# Technologies we care about policing. A bullet may only name a tool if the
# base resume already names it somewhere (bullets, skills, or project stacks).
_TECH_VOCAB = {
    "python", "sql", "r", "pytorch", "pyspark", "pandas", "numpy",
    "scikit-learn", "sklearn", "tensorflow", "keras",
    "langchain", "langgraph", "openai", "anthropic", "claude", "llm", "rag",
    "bert", "transformers", "hugging face", "huggingface", "chromadb",
    "pymupdf", "ada-002", "mlflow", "docker", "kubernetes", "ci/cd",
    "terraform", "ansible", "hadoop", "hive", "scala", "rust",
    "airflow", "dbt", "spark", "postgresql", "redshift", "snowflake",
    "bigquery", "databricks", "kafka", "azure", "aws", "gcp", "s3", "ec2",
    "tableau", "power bi", "powerbi", "plotly", "dash", "looker", "excel",
    "flask", "fastapi", "django", "react", "streamlit", "gradio", "git",
    "mcp", "sqlite", "mongodb", "opik", "langsmith", "sagemaker",
}


@dataclass
class Finding:
    kind: str        # fabricated_metric | unsupported_claim | skill_inflation
    severity: str    # error | warn
    bullet: str
    detail: str


@dataclass
class ValidationReport:
    ok: bool
    findings: list[Finding] = field(default_factory=list)
    provenance: dict[int, str] = field(default_factory=dict)   # bullet idx -> item id
    thresholds: dict = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    def summary(self) -> str:
        if self.ok:
            return f"clean ({len(self.provenance)} bullets, all traced)"
        by = {}
        for f in self.errors:
            by[f.kind] = by.get(f.kind, 0) + 1
        return "FAIL: " + ", ".join(f"{v}x {k}" for k, v in sorted(by.items()))

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "thresholds": self.thresholds,
            "provenance": self.provenance,
            "findings": [asdict(f) for f in self.findings],
        }


def _allowed_tech(tex_path: Path | str = BASE_TEX) -> set[str]:
    """Technologies the base resume actually names, anywhere in the document."""
    raw = strip_tex(Path(tex_path).read_text(encoding="utf-8", errors="replace")).lower()
    return {t for t in _TECH_VOCAB if t in raw}


def _best_match(bullet: str, items: list[CorpusItem]) -> tuple[float, CorpusItem | None]:
    best, best_item = 0.0, None
    b = bullet.lower()
    for it in items:
        r = SequenceMatcher(None, b, it.text.lower()).ratio()
        if r > best:
            best, best_item = r, it
    return best, best_item


def validate_bullets(
    bullets: list[str],
    items: list[CorpusItem],
    *,
    provenance_floor: float = PROVENANCE_FLOOR,
    strict_metrics: bool = STRICT_METRICS,
    tex_path: Path | str = BASE_TEX,
) -> ValidationReport:
    """Check tailored bullets against the corpus. No LLM calls."""
    legit_numbers = corpus_numbers(items)
    allowed_tech = _allowed_tech(tex_path)

    report = ValidationReport(
        ok=True,
        thresholds={
            "provenance_floor": provenance_floor,
            "strict_metrics": strict_metrics,
            "corpus_items": len(items),
            "legit_numbers": len(legit_numbers),
        },
    )

    for i, bullet in enumerate(bullets):
        plain = strip_tex(bullet)

        # 1. provenance
        score, src = _best_match(plain, items)
        if src is not None:
            report.provenance[i] = f"{src.id} ({score:.2f})"
        if score < provenance_floor:
            report.findings.append(Finding(
                kind="unsupported_claim", severity="error", bullet=plain[:120],
                detail=f"no corpus item above {provenance_floor:.2f} "
                       f"(best {score:.2f}"
                       + (f" -> {src.id}" if src else "") + ")",
            ))

        # 2. metric lock
        invented = numbers_in(plain) - legit_numbers
        # bare small integers are usually prose ("3 teams"), not claims
        invented = {n for n in invented if not (n.isdigit() and len(n) <= 1)}
        if invented:
            report.findings.append(Finding(
                kind="fabricated_metric",
                severity="error" if strict_metrics else "warn",
                bullet=plain[:120],
                detail=f"numbers not in corpus: {sorted(invented)}",
            ))

        # 3. skill floor
        low = plain.lower()
        named = {t for t in _TECH_VOCAB if re.search(rf"(?<![\w-]){re.escape(t)}(?![\w-])", low)}
        inflated = named - allowed_tech
        if inflated:
            report.findings.append(Finding(
                kind="skill_inflation", severity="error", bullet=plain[:120],
                detail=f"tech not in base resume: {sorted(inflated)}",
            ))

    report.ok = not report.errors
    return report


if __name__ == "__main__":
    from .corpus import load_corpus
    items = load_corpus()

    good = [
        "Deployed production RAG pipeline using LangChain and OpenAI API serving 500+ users with 60% latency reduction.",
        "Engineered PySpark feature pipelines processing 2M+ records from Redshift, improving data quality 40%.",
    ]
    bad = [
        "Deployed production RAG pipeline serving 5000+ users with 95% latency reduction.",   # invented metrics
        "Led a team of 12 engineers building Kubernetes microservices on Snowflake.",         # unsupported + inflation
    ]

    for label, bs in [("GOOD", good), ("BAD", bad)]:
        rep = validate_bullets(bs, items)
        print(f"\n=== {label} === {rep.summary()}")
        for f in rep.findings:
            print(f"  [{f.severity}] {f.kind}: {f.detail}")
            print(f"      {f.bullet[:90]}")
