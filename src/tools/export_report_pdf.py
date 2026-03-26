#!/usr/bin/env python3
"""Export reports/final_report.md to reports/final_report.pdf as a plain-text PDF."""

from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def main():
    root = Path(__file__).resolve().parents[2]
    src = root / "reports" / "final_report.md"
    dst = root / "reports" / "final_report.pdf"

    text = src.read_text(encoding="utf-8")

    c = canvas.Canvas(str(dst), pagesize=A4)
    width, height = A4

    # Try to render UTF-8 safely; fallback to Helvetica if font unavailable.
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", "C:/Windows/Fonts/DejaVuSans.ttf"))
        font_name = "DejaVuSans"
    except Exception:
        font_name = "Helvetica"

    c.setFont(font_name, 10)
    left_margin = 40
    top_margin = height - 40
    line_height = 13
    y = top_margin

    for raw_line in text.splitlines():
        line = raw_line.expandtabs(2)
        chunks = [line[i:i + 110] for i in range(0, len(line), 110)] or [""]
        for chunk in chunks:
            if y < 40:
                c.showPage()
                c.setFont(font_name, 10)
                y = top_margin
            c.drawString(left_margin, y, chunk)
            y -= line_height

    c.save()
    print(f"[OK] Wrote {dst}")


if __name__ == "__main__":
    main()
