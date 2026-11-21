"""Tailors your master resume + a cover letter to specific job links. Run from GitHub Actions (tailor.yml).
Reads secrets: MASTER_RESUME (text), ANTHROPIC_API_KEY, TELEGRAM_*. Sends the .docx files to your Telegram."""
import os, re, json, html, textwrap, requests
from pathlib import Path
from lib import *
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

# ---------- job description ----------
def strip_html(h):
    h = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", h)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", html.unescape(re.sub(r"<[^>]+>", " ", h)))).strip()

def jsonld_job(page):
    for m in re.finditer(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page):
        try: data = json.loads(m.group(1))
        except Exception: continue
        for d in (data if isinstance(data, list) else data.get("@graph", [data])):
            if isinstance(d, dict) and d.get("@type") == "JobPosting":
                org = d.get("hiringOrganization"); org = org.get("name") if isinstance(org, dict) else org
                return dict(title=d.get("title", ""), company=org or "", text=strip_html(d.get("description", "")))
    return None

def get_jd(url):
    u = url.strip()
    try:
        m = re.match(r"https://([^./]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?]+)(/job/[^?]+)", u)
        if m:
            t, wd, site, path = m.groups(); j = get_json(f"https://{t}.{wd}.myworkdayjobs.com/wday/cxs/{t}/{site}{path}")["jobPostingInfo"]
            return dict(title=j.get("title", ""), company=t, text=strip_html(j.get("jobDescription", "")))
        m = re.search(r"greenhouse\.io/([^/?]+)/jobs/(\d+)", u)
        if m:
            j = get_json(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}")
            return dict(title=j.get("title", ""), company=m.group(1), text=strip_html(j.get("content", "")))
        m = re.search(r"jobs\.lever\.co/([^/?]+)/([0-9a-f-]{36})", u)
        if m:
            j = get_json(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}")
            return dict(title=j.get("text", ""), company=m.group(1), text=j.get("descriptionPlain", "") + "\n" + "\n".join(x.get("text", "") + " " + strip_html(x.get("content", "")) for x in j.get("lists", [])))
        page = requests.get(u, timeout=40, headers=UA).text
        if (j := jsonld_job(page)) and len(j["text"]) > 200: return j
        title = (re.search(r"(?is)<title>(.*?)</title>", page) or [None, ""])[1]
        return dict(title=html.unescape(title).strip(), company="", text=strip_html(page)[:12000])
    except Exception as e:
        return dict(title="", company="", text="", error=str(e)[:150])

# ---------- Claude ----------
SYSTEM = """You tailor a student's resume and write a cover letter for ONE job. Hard rules:
1. TRUTH ONLY. Use only facts, employers, dates, tools, projects and numbers that appear in MASTER RESUME. Never invent experience, skills,
   metrics, titles or coursework. You may reorder, select, and reword. If the job wants something the resume lacks, do NOT claim it; list it in notes.
2. Resume bullets use the XYZ format when the master resume supports it: "Accomplished X, as measured by Y, by doing Z" written as one natural
   past-tense sentence starting with a strong verb. If there is no real metric, write a plain accurate bullet and add it to notes.bullets_needing_metrics.
3. ATS friendly: plain text, single column, standard section names (Education, Experience, Projects, Skills), no tables/icons/columns.
   Mirror the job's exact terminology only where it is true for this person (e.g. 'procurement', 'SAP', 'demand planning'). No keyword stuffing.
4. Keep resume to one page: at most 3-4 bullets for the most relevant roles, 2 for others, drop weakest projects. Put the most relevant items first.
5. Cover letter: 3 short paragraphs, 200-260 words, first person, specific to this company and role, concrete evidence from the resume,
   plain conversational voice like a sharp student writing it themselves. Avoid cliches and filler ("I am writing to express", "passionate",
   "excited to leverage", "dynamic", "synergy", "fast-paced"), avoid em dashes, avoid lists, vary sentence length. Do not claim facts about
   the company beyond what the job text says. Do not mention visa/sponsorship.
Return ONLY JSON: {"name":str,"contact":str,"summary":str (empty string if not useful, max 2 lines),
"education":[{"school":str,"line2":str,"dates":str,"extra":str}],
"experience":[{"title":str,"org":str,"location":str,"dates":str,"bullets":[str]}],
"projects":[{"name":str,"detail":str,"bullets":[str]}],"skills":[{"category":str,"items":str}],
"cover_letter":[str,str,str],
"notes":{"matched_keywords":[str],"job_requirements_not_in_resume":[str],"bullets_needing_metrics":[str]}}"""

def call_claude(master, jd, title, company):
    msgs = [{"role": "user", "content": f"JOB TITLE: {title}\nCOMPANY: {company}\n\nJOB DESCRIPTION:\n{jd[:9000]}\n\nMASTER RESUME:\n{master}"}]
    last = None
    for attempt in range(3):                                   # the model occasionally returns slightly broken JSON: retry instead of failing
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=180, headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 8000, "temperature": 0.3 if attempt else 0.7, "system": SYSTEM, "messages": msgs})
        if r.status_code != 200: raise RuntimeError(f"Anthropic API {r.status_code}: {r.text[:200]}")
        txt = "".join(b.get("text", "") for b in r.json()["content"])
        try: return json.loads(txt[txt.index("{"): txt.rindex("}") + 1], strict=False)
        except Exception as e:
            last = e; msgs = msgs[:1] + [{"role": "assistant", "content": txt}, {"role": "user", "content": "That was not valid JSON (" + str(e)[:80] + "). Return the complete answer again as ONE valid JSON object only: escape every double quote inside strings with a backslash, no line breaks inside strings, no trailing commas, no text outside the JSON."}]
    raise RuntimeError(f"model returned invalid JSON 3 times: {last}")

def unsupported_numbers(out, master):
    have = set(re.findall(r"\d[\d,.]*%?", master))
    mine = out["summary"] + " ".join(b for e in out["experience"] for b in e["bullets"]) + " ".join(b for p in out["projects"] for b in p["bullets"])
    return sorted({n.rstrip(".,") for n in re.findall(r"\d[\d,.]*%?", mine)} - {h.rstrip(".,") for h in have})

# ---------- Word files (plain, ATS-safe) ----------
def _doc():
    d = Document(); s = d.sections[0]
    s.left_margin = s.right_margin = Inches(0.75); s.top_margin = s.bottom_margin = Inches(0.6)
    st = d.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(10.5)
    st.paragraph_format.space_after = Pt(2); return d
def _para(d, text="", bold=False, size=None, align=None, after=None):
    p = d.add_paragraph(); r = p.add_run(text); r.bold = bold
    if size: r.font.size = Pt(size)
    if align: p.alignment = align
    if after is not None: p.paragraph_format.space_after = Pt(after)
    return p
def _head(d, t):
    p = _para(d, t.upper(), bold=True, size=11); p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(2); return p
def _bullet(d, t):
    p = d.add_paragraph(t, style="List Bullet"); p.paragraph_format.space_after = Pt(1); return p

def build_resume(o, path):
    d = _doc(); _para(d, o["name"], bold=True, size=16, align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
    _para(d, o["contact"], align=WD_ALIGN_PARAGRAPH.CENTER, after=4)
    if o.get("summary"): _head(d, "Summary"); _para(d, o["summary"])
    _head(d, "Education")
    for e in o["education"]:
        _para(d, f"{e['school']}  |  {e['dates']}", bold=True, after=0); _para(d, e["line2"], after=0)
        if e.get("extra"): _para(d, e["extra"], after=0)
    _head(d, "Experience")
    for e in o["experience"]:
        _para(d, f"{e['title']}  |  {e['org']}", bold=True, after=0); _para(d, f"{e['location']}  |  {e['dates']}", after=1)
        for b in e["bullets"]: _bullet(d, b)
    if o["projects"]:
        _head(d, "Projects")
        for p in o["projects"]:
            _para(d, f"{p['name']}  |  {p['detail']}", bold=True, after=0)
            for b in p["bullets"]: _bullet(d, b)
    _head(d, "Skills")
    for s in o["skills"]: _para(d, f"{s['category']}: {s['items']}", after=1)
    d.save(path)

def build_cover(o, company, path):
    d = _doc(); _para(d, o["name"], bold=True, size=13, after=0); _para(d, o["contact"], after=10)
    _para(d, "Dear Hiring Team," if not company else f"Dear {company} Hiring Team,", after=6)
    for para in o["cover_letter"]: _para(d, para, after=6)
    _para(d, "Sincerely,", after=0); _para(d, o["name"]); d.save(path)

def send_doc(path, caption):
    if DRY_RUN or not (TG_TOKEN and TG_CHAT): print("(not sent)", path); return
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendDocument", timeout=60,
                          data={"chat_id": TG_CHAT, "caption": caption[:1000], "parse_mode": "HTML"}, files={"document": f})
    if r.status_code != 200: raise RuntimeError(f"Telegram {r.status_code}: {r.text[:150]}")

def slug(s): return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")[:40] or "job"

def tailor_urls(urls, known=None, auto=False):
    """Tailor a resume + cover letter for each job link and send both files to Telegram."""
    master = os.environ.get("MASTER_RESUME", "").strip()           # optional override; normally read live from your portfolio
    if not master:
        import portfolio; master = portfolio.master_resume()
    if not master or "TODO" in master or not os.environ.get("ANTHROPIC_API_KEY"):
        if not auto:
            telegram("❌ Tailoring needs the ANTHROPIC_API_KEY secret and a resume it can read: link your resume PDF on your portfolio page, or set MASTER_RESUME. See README step 8.")
        return 0
    known = known if known is not None else {j["url"]: j for j in jload("jobs.json", [])}
    out_dir = Path("/tmp/applications"); out_dir.mkdir(exist_ok=True); done = 0
    for u in urls:
        try:
            jd = get_jd(u); k = known.get(u, {})
            title = k.get("title") or jd["title"] or "the role"; company = k.get("company") or jd["company"] or ""
            if len(jd["text"]) < 200:
                if auto: continue          # never tailor blind in automatic mode
                telegram(f"⚠️ Couldn't read the job description at {html.escape(u)} ({jd.get('error', 'page needs a login or JavaScript')}). "
                         "Paste the text into the workflow's 'job_text' box, or I'll tailor from the title only.")
                jd["text"] = os.environ.get("JOB_TEXT", "") or f"(no description available) {title}"
            o = call_claude(master, jd["text"], title, company)
            base = f"{slug(company)}-{slug(title)}"
            rp, cp = out_dir / f"Resume-{base}.docx", out_dir / f"CoverLetter-{base}.docx"
            build_resume(o, rp); build_cover(o, company, cp)
            bad = unsupported_numbers(o, master); n = o.get("notes", {})
            cap = (f"<b>{html.escape(title)}</b> · {html.escape(company)}\n<a href=\"{html.escape(u, quote=True)}\">Job link</a>\n"
                   f"Not in your resume (don't claim): {html.escape(', '.join(n.get('job_requirements_not_in_resume', [])[:6]) or 'nothing major')}\n"
                   + (f"⚠️ Check these numbers, not found in your master resume: {html.escape(', '.join(bad))}\n" if bad else "")
                   + (f"Add a real metric to: {html.escape('; '.join(n.get('bullets_needing_metrics', [])[:3]))}" if n.get("bullets_needing_metrics") else ""))
            send_doc(rp, cap); send_doc(cp, "Cover letter · read it once and change anything that doesn't sound like you"); done += 1
        except Exception as e:
            telegram(f"❌ Tailoring failed for {html.escape(u)}: {html.escape(str(e)[:200])}")
    return done

def main():
    urls = [u.strip() for u in re.split(r"[\s,]+", os.environ.get("JOB_URLS", "")) if u.startswith("http")]
    tailor_urls(urls)

if __name__ == "__main__": main()
