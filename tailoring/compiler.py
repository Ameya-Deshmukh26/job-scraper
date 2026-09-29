"""Save tailored LaTeX to the resume folder and attempt pdflatex compilation."""
import re
import shutil
import subprocess
from pathlib import Path

from config import RESUME_DIR, YOUR_NAME

OUTPUT_DIR = RESUME_DIR   # RESUME_OUTPUT_DIR in search_profile.py, else ./resumes


def save_and_compile(latex: str, company: str) -> dict:
    """
    Write <stem>.tex to Downloads, attempt pdflatex.
    Returns:
      tex_path  – always set
      pdf_path  – set only when pdflatex succeeded
      error     – None on full success, message otherwise
    """
    safe = re.sub(r"[^A-Za-z0-9_-]", "", company).title() or "Company"
    who = re.sub(r"[^A-Za-z0-9]+", "_", YOUR_NAME).strip("_") or "Resume"
    stem = f"{who}_{safe}"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tex_path = OUTPUT_DIR / f"{stem}.tex"
    pdf_path = OUTPUT_DIR / f"{stem}.pdf"

    tex_path.write_text(latex, encoding="utf-8")

    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        return {"tex_path": str(tex_path), "pdf_path": None, "error": "pdflatex not found"}

    try:
        subprocess.run(
            [
                pdflatex,
                "-interaction=nonstopmode",
                "-output-directory", str(OUTPUT_DIR),
                str(tex_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {"tex_path": str(tex_path), "pdf_path": None, "error": "pdflatex timed out"}
    except Exception as exc:
        return {"tex_path": str(tex_path), "pdf_path": None, "error": str(exc)}

    if pdf_path.exists():
        return {"tex_path": str(tex_path), "pdf_path": str(pdf_path), "error": None}

    return {"tex_path": str(tex_path), "pdf_path": None, "error": "pdflatex ran but PDF not created"}
