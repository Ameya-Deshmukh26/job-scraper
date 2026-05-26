"""Save tailored LaTeX to Downloads and attempt pdflatex compilation."""
import re
import shutil
import subprocess
from pathlib import Path

OUTPUT_DIR = Path("C:/Users/ameya/Downloads")


def save_and_compile(latex: str, company: str) -> dict:
    """
    Write <stem>.tex to Downloads, attempt pdflatex.
    Returns:
      tex_path  – always set
      pdf_path  – set only when pdflatex succeeded
      error     – None on full success, message otherwise
    """
    safe = re.sub(r"[^A-Za-z0-9_-]", "", company).title() or "Company"
    stem = f"Ameya_Deshmukh_{safe}"
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
