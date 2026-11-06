"""Builds docs/FINAL_REPORT.pdf from docs/FINAL_REPORT.md. Run from the docs/ folder."""

from pathlib import Path

import markdown
from xhtml2pdf import pisa

HERE = Path(__file__).resolve().parent
MD_PATH = HERE / "FINAL_REPORT.md"
PDF_PATH = HERE / "FINAL_REPORT.pdf"
LOGO_PATH = HERE / "assets" / "esprit_logo.png"

body_md = MD_PATH.read_text(encoding="utf-8")
# the logo is placed in the HTML header template instead, so drop the inline markdown image
body_md = body_md.replace("![ESPRIT](assets/esprit_logo.png)\n\n", "")

body_html = markdown.markdown(
    body_md, extensions=["tables", "fenced_code", "sane_lists"]
)

html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 2.2cm 2cm 2cm 2cm;
    @frame header_frame {{
      -pdf-frame-content: header_content;
      top: 0.8cm; left: 2cm; right: 2cm; height: 1.6cm;
    }}
    @frame footer_frame {{
      -pdf-frame-content: footer_content;
      bottom: 0.8cm; left: 2cm; right: 2cm; height: 1cm;
    }}
  }}
  body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1a1a1a; }}
  h1 {{ font-size: 19pt; margin-top: 0; margin-bottom: 4pt; color: #111; }}
  h2 {{ font-size: 14pt; margin-top: 16pt; margin-bottom: 6pt; color: #111; border-bottom: 1px solid #C90C0F; padding-bottom: 2pt; }}
  h3 {{ font-size: 12pt; margin-top: 12pt; margin-bottom: 4pt; color: #111; }}
  p {{ margin: 4pt 0; text-align: justify; }}
  blockquote {{ background: #f5f5f5; border-left: 3px solid #C90C0F; margin: 8pt 0; padding: 6pt 10pt; font-size: 9.5pt; color: #444; }}
  table {{ border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt; }}
  th, td {{ border: 0.5pt solid #999; padding: 4pt 6pt; text-align: left; }}
  th {{ background: #f0f0f0; font-weight: bold; }}
  code {{ font-family: Courier, monospace; background: #f3f3f3; padding: 1pt 3pt; font-size: 9pt; }}
  pre {{ font-family: Courier, monospace; background: #f3f3f3; padding: 6pt; font-size: 8.5pt; white-space: pre-wrap; }}
  hr {{ border: none; border-top: 0.5pt solid #ccc; margin: 10pt 0; }}
  ul, ol {{ margin: 4pt 0; padding-left: 16pt; }}
  li {{ margin: 2pt 0; }}
  img {{ max-width: 100%; }}
  #header_content {{ text-align: right; }}
  #header_content img {{ height: 32px; max-width: none; }}
  #footer_content {{ text-align: center; font-size: 8pt; color: #888; }}
</style>
</head>
<body>
  <div id="header_content"><img src="{LOGO_PATH.as_posix()}"/></div>
  <div id="footer_content">DressMe, Advanced Data Science Project, Final Technical Report, page <pdf:pagenumber/> of <pdf:pagecount/></div>
  {body_html}
</body>
</html>
"""

with open(PDF_PATH, "wb") as f:
    result = pisa.CreatePDF(html, dest=f, path=str(HERE) + "/")

if result.err:
    raise SystemExit(f"{result.err} error(s) while generating PDF")

print(f"Wrote {PDF_PATH}")
