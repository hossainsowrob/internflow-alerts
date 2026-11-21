"""One function per job source. Each returns a list of postings:
{id, company, title, location, url, desc, source, posted (unix seconds or None), board (board key or None)}"""
import os, re, csv, time, datetime as dt, requests
from lib import *
import config as C

INTERN_RE = re.compile(r"\b(intern|interns|internship|co-?op|coop)\b", re.I)
US_RE = re.compile(r",\s*(A[KLRZ]|C[AOT]|D[CE]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b"
                   r"|\bremote\b|\busa?\b|united states|\bNYC\b|\bSF\b", re.I)
SIMPLIFY_URL = os.environ.get("SIMPLIFY_LISTINGS_URL",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/.github/scripts/listings.json")

def iso(v):
    try: return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception: return None

def P(id, company, title, location, url, source, desc="", posted=None, board=None):
    return dict(id=str(id), company=company or "", title=title or "", location=location or "", url=url or "",
                desc=desc or "", source=source, posted=posted, board=board)

# ---------- 1. SimplifyJobs community feed (aggregates thousands of company career pages) ----------
def simplify():
    out = []
    for x in requests.get(SIMPLIFY_URL, timeout=120, headers=UA).json():
        if not (x.get("active") and x.get("is_visible")): continue
        if not (C.TERMS & set(x.get("terms") or [])): continue
        if x.get("sponsorship") == "U.S. Citizenship is Required": continue
        deg = x.get("degrees") or []
        if deg and "Bachelor's" not in deg and "Associate's" not in deg: continue      # master's/PhD only
        locs = x.get("locations") or []
        if locs and not any(US_RE.search(l) for l in locs): continue
        out.append(P("sf-" + x["id"], x["company_name"], x["title"], ", ".join(locs[:3]), x["url"], "SimplifyJobs",
                     posted=x.get("date_posted")))
    return out

# ---------- 2. Company career sites via their applicant-tracking systems (free public APIs) ----------
def derive_board(url):
    """From any job URL, work out the company's own board so we can poll it directly."""
    m = re.match(r"https://([^./]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?]+)", url or "")
    if m and m.group(3) not in ("job", "jobs"): return ("workday", "", f"https://{m.group(1)}.{m.group(2)}.myworkdayjobs.com/{m.group(3)}")
    for typ, pat in (("greenhouse", r"https://(?:job-)?boards(?:\.eu)?\.greenhouse\.io/([^/?]+)"),
                     ("lever", r"https://jobs\.lever\.co/([^/?]+)"), ("ashby", r"https://jobs\.ashbyhq\.com/([^/?]+)"),
                     ("smartrecruiters", r"https://(?:jobs|careers)\.smartrecruiters\.com/([^/?]+)")):
        m = re.match(pat, url or "")
        if m and m.group(1) not in ("embed",): return (typ, m.group(1), "")
    return None

def parse_board(typ, data, name, bkey, url=""):
    out = []
    def add(i, title, loc, link, desc="", posted=None):
        if INTERN_RE.search(title or ""): out.append(P(f"{typ[:2]}-{key(name).replace(' ', '')}-{i}", name, title, loc, link, typ.capitalize(), desc, posted, bkey))
    if typ == "greenhouse":
        for j in data.get("jobs", []):
            add(j["id"], j["title"], (j.get("location") or {}).get("name"), j["absolute_url"], posted=iso(j.get("first_published")))
    elif typ == "lever":
        for j in data:
            add(j["id"], j["text"], (j.get("categories") or {}).get("location"), j["hostedUrl"], j.get("descriptionPlain", ""), (j.get("createdAt") or 0) / 1000 or None)
    elif typ == "ashby":
        for j in data.get("jobs", []):
            add(j["id"], j["title"], j.get("location"), j["jobUrl"], j.get("descriptionPlain", ""), iso(j.get("publishedAt")))
    elif typ == "smartrecruiters":
        for j in data.get("content", []):
            loc = ", ".join(x for x in ((j.get("location") or {}).get("city"), (j.get("location") or {}).get("region")) if x)
            add(j["id"], j["name"], loc, f"https://jobs.smartrecruiters.com/{url}/{j['id']}", posted=iso(j.get("releasedDate")))
    elif typ == "workday":
        base = url.rsplit("/", 1)[0]; site = url.rsplit("/", 1)[1]
        for j in data:
            t = (j.get("postedOn") or "").lower(); now = time.time()
            posted = None if "today" in t else now - 86400 if "yesterday" in t else (now - int(m.group(1)) * 86400 if (m := re.search(r"(\d+)\+? days", t)) else None)
            add(j["externalPath"], j["title"], j.get("locationsText"), f"{base}/{site}{j['externalPath']}", posted=posted)
    return out

def poll_board(name, typ, token, url):
    bkey = f"{key(name)}|{typ}"
    if typ == "greenhouse": data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    elif typ == "lever": data = get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    elif typ == "ashby": data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    elif typ == "smartrecruiters": data = get_json(f"https://api.smartrecruiters.com/v1/companies/{token}/postings?q=intern&limit=100"); url = token
    elif typ == "workday":
        m = re.match(r"https://([^.]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?]+)", url)
        tenant, wd, site = m.groups(); base = f"https://{tenant}.{wd}.myworkdayjobs.com"; data = []
        for off in range(0, 160, 20):
            for wait in (0, 4, 10):
                time.sleep(wait); r = requests.post(f"{base}/wday/cxs/{tenant}/{site}/jobs", timeout=40, headers=UA,
                                  json={"appliedFacets": {}, "limit": 20, "offset": off, "searchText": "intern"})
                if r.status_code != 429: break      # rate limited: wait and retry
            r.raise_for_status(); page = r.json().get("jobPostings", []); data += page
            if len(page) < 20: break
        url = f"{base}/{site}"
    else: return []
    return parse_board(typ, data, name, bkey, url)

# ---------- 3. Job-board aggregators (need free API keys; see README) ----------
def adzuna():
    app, k = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY"); out = []
    if not (app and k): return out
    for q in C.SEARCHES:
        for page in (1, 2):
            r = requests.get(f"https://api.adzuna.com/v1/api/jobs/us/search/{page}", timeout=40, params={
                "app_id": app, "app_key": k, "what": q, "max_days_old": C.ADZUNA_MAX_AGE_DAYS, "results_per_page": 50, "sort_by": "date"})
            if r.status_code != 200: break
            for j in r.json().get("results", []):
                if INTERN_RE.search(j.get("title", "")):
                    out.append(P("az-" + str(j["id"]), (j.get("company") or {}).get("display_name"), re.sub(r"</?strong>", "", j["title"]),
                                 (j.get("location") or {}).get("display_name"), j["redirect_url"], "Adzuna", j.get("description", ""), iso(j.get("created"))))
    return out

def jsearch():
    """Google-for-Jobs data: LinkedIn, Indeed, Glassdoor, ZipRecruiter, company sites. Free tier is small, so it runs
    only on the first scan of each day and uses the first JSEARCH_QUERIES searches."""
    k, out = os.environ.get("RAPIDAPI_KEY"), []
    if not k or os.environ.get("RUN_JSEARCH") != "1": return out
    for q in C.SEARCHES[:int(os.environ.get("JSEARCH_QUERIES", "5"))]:
        r = requests.get("https://jsearch.p.rapidapi.com/search", timeout=60, headers={"X-RapidAPI-Key": k, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"},
                         params={"query": f"{q} in USA", "date_posted": "3days", "num_pages": "1"})
        if r.status_code != 200: continue
        for j in r.json().get("data", []):
            if INTERN_RE.search(j.get("job_title", "")) and j.get("job_apply_link"):
                loc = ", ".join(x for x in (j.get("job_city"), j.get("job_state")) if x) or ("Remote" if j.get("job_is_remote") else "")
                out.append(P("js-" + j["job_id"], j.get("employer_name"), j["job_title"], loc, j["job_apply_link"],
                             "via " + (j.get("job_publisher") or "JSearch"), (j.get("job_description") or "")[:3000], j.get("job_posted_at_timestamp")))
    return out


# ---------- check the job's own page for its real posting date ----------
def verify_age(url):
    """Return the date (datetime.date) the employer's page says the job was posted, or None if it can't be found."""
    import datetime as dt, html as H
    try: page = requests.get(url, timeout=20, headers=UA).text
    except Exception: return None
    cands = re.findall(r'"datePosted"\s*:\s*"([^"]+)"', page)
    txt = H.unescape(re.sub(r"(?s)<[^>]+>", " ", page))
    cands += re.findall(r"Posted(?: on)?:?\s+([A-Z][a-z]{2,8}\.? \d{1,2}, \d{4})", txt)
    cands += re.findall(r"Posted(?: on)?:?\s+(\d{4}-\d{2}-\d{2})", txt)
    for c in cands:
        c = c.strip()
        for fmt, n in (("%Y-%m-%d", 10), ("%B %d, %Y", None), ("%b %d, %Y", None), ("%b. %d, %Y", None)):
            try: return dt.datetime.strptime(c[:n] if n else c, fmt).date()
            except ValueError: pass
    return None
