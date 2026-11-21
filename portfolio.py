"""Reads your contact details and resume from your portfolio site, so you only ever edit the portfolio.
Optional, for exact control: add this to your portfolio page (any place in the HTML) and fill it in:
<script type="application/json" id="internflow-profile">{"first":"","last":"","email":"","phone":"","city":"","state":"","zip":"","address":""}</script>"""
import os, re, io, json, html as H, requests
from urllib.parse import urljoin
from lib import UA

URL = os.environ.get("PORTFOLIO_URL", "https://hossainsowrob.github.io")

def _text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", "\n", raw)
    return re.sub(r"\n\s*\n+", "\n", H.unescape(raw)).strip()

def read(url=URL):
    out = {"text": "", "resume_url": "", "resume_text": ""}
    raw = requests.get(url, timeout=30, headers=UA).text
    out["text"] = _text(raw)
    m = re.search(r'(?is)<script[^>]+id=["\']internflow-profile["\'][^>]*>(.*?)</script>', raw)
    if m:
        try: out.update({k: str(v) for k, v in json.loads(m.group(1)).items()})
        except Exception: pass
    if not out.get("email"):
        m = re.search(r'mailto:([^"\'?>\s]+)', raw, re.I) or re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", out["text"]); out["email"] = (m.group(1) if m and m.lastindex else m.group(0)) if m else ""
    for a in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw):
        href, label = a.group(1), _text(a.group(2))
        if re.search(r"linkedin\.com/in/", href, re.I): out.setdefault("linkedin", href.split("?")[0])
        if re.search(r"github\.com/[^/]+/?$", href, re.I): out.setdefault("github", href)
        if not out["resume_url"] and re.search(r"resum|\bcv\b", href + " " + label, re.I) and re.search(r"\.(pdf|docx?)(\?|$)", href, re.I): out["resume_url"] = urljoin(url, href)
    if out["resume_url"]:
        try:
            b = requests.get(out["resume_url"], timeout=60, headers=UA).content
            if out["resume_url"].lower().split("?")[0].endswith(".pdf"):
                from pypdf import PdfReader
                out["resume_text"] = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(b)).pages)
            else:
                from docx import Document
                out["resume_text"] = "\n".join(p.text for p in Document(io.BytesIO(b)).paragraphs)
        except Exception as e: out["resume_error"] = str(e)[:100]
    return out

def master_resume():
    """Best available master resume text, or ''. Uses the resume file linked on the portfolio, else the portfolio's own text."""
    try: d = read()
    except Exception: return ""
    if len(d.get("resume_text", "")) > 300: return d["resume_text"]
    return d["text"] if len(d["text"]) > 500 else ""
