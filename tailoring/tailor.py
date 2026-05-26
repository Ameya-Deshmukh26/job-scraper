"""Call Claude Opus 4.7 to tailor Ameya's LaTeX resume to a job description."""
import os
import re
from pathlib import Path

import anthropic


_SYSTEM = """\
You are a professional resume writer. Tailor Ameya Deshmukh's LaTeX resume to the job description below.

Rules:
1. Keep ALL LaTeX commands and section structure exactly as-is.
   Only change text inside \\resumeItem{...}, \\resumeSubheading{...} titles/dates, and the Skills section values.
2. Each \\resumeItem bullet must be 20-30 words with a measurable outcome where possible.
3. Mirror keywords from the JD naturally — do NOT invent fake experience or fake metrics.
4. In the Skills section reorder technologies so the most relevant ones appear first.
5. Keep all contact information unchanged.
6. Return ONLY the complete LaTeX source — no explanations, no markdown fences.
7. On the very last line add exactly this comment (replace XX with a number):
   %MATCH_SCORE: XX%
   where XX is your 0-100 estimate of keyword/skill alignment between the tailored resume and the JD.\
"""


def tailor_resume(jd_text: str, company: str) -> tuple[str, int]:
    """Return (tailored_latex_string, match_percent_int)."""
    from config import ANTHROPIC_API_KEY, BASE_TEX_PATH

    api_key = os.environ.get("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. Add it to config.py or set the env var."
        )

    base_tex = Path(BASE_TEX_PATH).read_text(encoding="utf-8")
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=8192,
        thinking={"type": "adaptive"},
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Tailor my resume for this {company} role.\n\n"
                    f"JOB DESCRIPTION:\n{jd_text}\n\n"
                    f"BASE RESUME (LaTeX):\n{base_tex}"
                ),
            }
        ],
    )

    latex = next(
        (block.text for block in response.content if block.type == "text"), ""
    )

    m = re.search(r"%MATCH_SCORE:\s*(\d+)%", latex)
    score = int(m.group(1)) if m else 75

    # Strip the score comment from the output .tex file
    latex = re.sub(r"\s*%MATCH_SCORE:.*$", "", latex, flags=re.MULTILINE).rstrip()

    return latex, score
