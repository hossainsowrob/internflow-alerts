"""Finds each watchlist company's own job board (Greenhouse / Lever / Ashby / SmartRecruiters) so new postings are caught
directly. Workday boards are picked up from job links and from `career_url` in companies.csv. Writes boards_auto.csv.
Runs weekly on GitHub Actions. Names are verified where the API shows a company name; guesses are marked."""
import csv, re, time, html
from concurrent.futures import ThreadPoolExecutor
from lib import *
from sources_fetch import derive_board

def candidates(name):
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("&", " and ")).split() if w not in ("inc", "llc", "corp", "corporation", "company", "co", "the", "and")]
    out = ["".join(words), "-".join(words)]
    return list(dict.fromkeys(s for s in out if len(s) > 2))

WD_HOSTS = (1, 5, 3, 12, 501, 2, 103, 4)
def probe_workday(name):
    """Workday boards live at https://TENANT.wdN.myworkdayjobs.com/SITE. Try the company name as the tenant on each data center,
    follow the redirect to learn the SITE, and confirm with Workday's own jobs endpoint. Marked as a guess (tenant names can differ)."""
    for s in candidates(name)[:1]:
        for n in WD_HOSTS:
            base = f"https://{s}.wd{n}.myworkdayjobs.com"
            try: root = requests.get(base + "/", timeout=8, headers=UA, allow_redirects=True)
            except Exception: continue
            m = re.search(r"myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([^/?#]+)", root.url)
            sites = ([m.group(1)] if m else []) + ["External", "Careers", "careers", s + "careers", s.capitalize() + "Careers"]
            for site in dict.fromkeys(x for x in sites if x and x.lower() not in ("login", "wday")):
                try:
                    r = requests.post(f"{base}/wday/cxs/{s}/{site}/jobs", timeout=12, headers=UA, json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
                    if r.status_code == 200 and r.json().get("total", 0) > 0: return ("workday", "", f"{base}/{site}", "guess")
                except Exception: pass
    return None

def probe(name):
    t = tokens(name)
    for s in candidates(name):
        try:   # Greenhouse: the board endpoint returns the company name, so we can verify it
            r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{s}", timeout=15, headers=UA)
            if r.status_code == 200 and (n := r.json().get("name")) and (name_matches(t, tokens(n)) or name_matches(tokens(n), t)):
                return ("greenhouse", s, "", "verified")
        except Exception: pass
        try:   # SmartRecruiters: postings include the company name
            r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=1", timeout=15, headers=UA)
            if r.status_code == 200 and r.json().get("content"):
                cn = r.json()["content"][0].get("company", {}).get("name", "")
                if name_matches(t, tokens(cn)) or name_matches(tokens(cn), t): return ("smartrecruiters", r.json()["content"][0]["company"].get("identifier", s), "", "verified")
        except Exception: pass
        for typ, url in (("lever", f"https://api.lever.co/v0/postings/{s}?mode=json"), ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{s}")):
            try:   # Lever/Ashby show no company name; accept only an exact slug with live jobs, marked as a guess
                r = requests.get(url, timeout=15, headers=UA)
                if r.status_code == 200 and (r.json() if typ == "lever" else r.json().get("jobs")): return (typ, s, "", "guess")
            except Exception: pass
    return probe_workday(name)

def run():
    comps = list(csv.DictReader(open(ROOT / "companies.csv")))
    state = jload("discover_state.json", {})                     # company -> last failed probe time
    try: auto = {r["company"]: r for r in csv.DictReader(open(ROOT / "boards_auto.csv"))}
    except FileNotFoundError: auto = {}
    manual = {r["company"] for r in csv.DictReader(open(ROOT / "sources.csv"))}
    todo = []
    for c in comps:
        n = c["name"]
        if n in auto or n in manual: continue
        d = derive_board(c.get("career_url", ""))
        if d: auto[n] = dict(company=n, type=d[0], token=d[1], url=d[2], confidence="from career_url"); continue
        if time.time() - state.get(n, 0) > 30 * 86400: todo.append(n)
    with ThreadPoolExecutor(8) as ex: res = list(ex.map(probe, todo))
    found = 0
    for n, r in zip(todo, res):
        if r: auto[n] = dict(company=n, type=r[0], token=r[1], url=r[2], confidence=r[3]); found += 1
        else: state[n] = time.time()
    with open(ROOT / "boards_auto.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["company", "type", "token", "url", "confidence"]); w.writeheader(); w.writerows(auto.values())
    jsave("discover_state.json", state)
    missing = [c["name"] for c in comps if c["name"] not in auto and c["name"] not in manual]
    telegram(f"🔎 InternFlow board discovery: found direct job boards for {found} more companies. "
             f"{len(comps) - len(missing)} of {len(comps)} companies are now tracked directly.\n"
             f"{len(missing)} use career sites I can't read automatically (they are still covered through Simplify/Adzuna/JSearch, with some delay). "
             f"To track one directly, paste its careers link in companies.csv (column career_url) if it is Workday/Greenhouse/Lever/Ashby."
             + (f"\nExamples: {html.escape(', '.join(missing[:25]))}" if missing else ""))
if __name__ == "__main__": run()
