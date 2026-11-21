"""InternFlow scanner. Runs on GitHub Actions 4x/day. Pulls internships from many sources, keeps the ones that fit
you at companies that sponsor H-1B/PERM, saves everything to jobs.json (dashboard) and sends new ones to Telegram."""
import os, re, csv, json, html, time, datetime as dt, traceback
from zoneinfo import ZoneInfo
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from lib import *
import config as C
import sources_fetch as S

# ---------- employer / sponsor matching ----------
class EmployerIndex:
    def __init__(self, rows):                                   # rows: [norm_key, name, lca, lca_field, perm, perm_field]
        self.by_first = defaultdict(list)
        for r in rows:
            t = r[0].split()
            if t: self.by_first[t[0]].append((t, r))
    def match(self, names):
        hits = {}
        for n in names:
            t = tokens(n)
            for et, r in self.by_first.get(t[0] if t else "", []):
                if name_matches(t, et, 3): hits[r[0]] = r
        if not hits: return None
        v = list(hits.values())
        return dict(lca=sum(r[2] for r in v), lca_f=sum(r[3] for r in v), perm=sum(r[4] for r in v), perm_f=sum(r[5] for r in v),
                    names=sorted({r[1] for r in v})[:3])

def classify(m):
    if m is None: return "Needs review"
    if m["lca_f"] + m["perm_f"] >= C.MIN_FIELD_CASES_NEW_COMPANY: return "Sponsors in your field"
    if m["lca"] + m["perm"] >= 10: return "Sponsors (other roles)"
    return "Weak sponsor history"
def evidence(m):
    if m is None: return "No DOL match found (add legal name/alias in companies.csv)"
    return f"DOL certified: {m['lca']} H-1B ({m['lca_f']} in your field), {m['perm']} PERM/green-card ({m['perm_f']} in your field) · {m['names'][0]}"
BADGE = {"Sponsors in your field": "✅", "Sponsors (other roles)": "🟡", "Weak sponsor history": "🔸"}

# ---------- fit scoring ----------
def has(text, kw): return re.search(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])", text) is not None
def score(p):
    title, text = p["title"].lower(), (p["title"] + " " + p["desc"]).lower()
    if any(has(title, b) for b in C.BAD_TITLE): return 0, []
    hits = sorted([(v, k) for k, v in C.TITLE_KEYWORDS.items() if has(title, k)], reverse=True)
    pts = min(60, sum(v for v, _ in hits[:2])); why = ["title: " + ", ".join(k for _, k in hits[:3])] if hits else []
    sk = [(lab, v) for k, (lab, v) in C.PROFILE_SKILLS.items() if has(text, k)]
    pts += min(30, sum(v for _, v in sk))
    if sk:
        why.append("skills: " + ", ".join(l for l, _ in sk[:4]))
        if any(l in ("SAP", "Excel VBA", "requisitions", "procurement") for l, _ in sk): why.append("builds on your Flowserve SAP/VBA/procurement work")
    if re.search(r"\b(summer|2027)\b", title): pts += 5
    return min(pts + 10, 100), why

def norm_posted(v):
    try:
        v = float(v)
        return v / 1000 if v > 1e12 else v
    except Exception: return None

# ---------- main ----------
def run():
    now = time.time(); today = dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()   # "today" = Eastern calendar day
    comps = list(csv.DictReader(open(ROOT / "companies.csv")))
    jobs = jload("jobs.json", []); state = jload("state.json", {"seen": {}, "boards": []})
    seen, known_boards = state["seen"], set(state["boards"]); prev_day = state.get("day", {})
    seen_urls = {j["url"] for j in jobs}; seen_titles = {key(j["company"]) + "|" + j["title"].lower().strip() for j in jobs}

    wl = defaultdict(list)                                       # first token -> [(tokens, company)]
    for c in comps:
        for n in [c["name"], c.get("legal_name", "")] + [a for a in (c.get("aliases") or "").split("|") if a]:
            t = tokens(n)
            if t: wl[t[0]].append((t, c))
    def resolve(name):
        t = tokens(name)
        return next((c for ct, c in wl.get(t[0] if t else "", []) if name_matches(ct, t)), None)

    emp_rows = jload("employers.json", None); employers = EmployerIndex(emp_rows) if emp_rows else None
    status = {}
    for c in comps:
        m = employers.match([c["name"], c.get("legal_name", "")] + [a for a in (c.get("aliases") or "").split("|") if a]) if employers else None
        status[c["name"]] = (classify(m), evidence(m)) if employers else ("Unverified", "Sponsor data not loaded yet")

    report, errors = [], []
    postings = S.simplify(); report.append(f"Simplify {len(postings):,}")
    boards = {}
    for p in postings:
        d = S.derive_board(p["url"])
        if d: c = resolve(p["company"]); boards[d] = (c["name"] if c else p["company"])
    for fn in ("sources.csv", "boards_auto.csv"):
        try:
            for r in csv.DictReader(open(ROOT / fn)): boards[(r["type"], r["token"], r["url"])] = r["company"]
        except FileNotFoundError: pass
    for c in comps:
        d = S.derive_board(c.get("career_url", ""))
        if d: boards[d] = c["name"]
    covered = {rc["name"] for n in boards.values() if (rc := resolve(n))}
    missing = [c["name"] for c in comps if c["name"] not in covered]

    def poll(item):
        (typ, tok, url), name = item
        try: return S.poll_board(name, typ, tok, url), None
        except Exception as e: return [], f"{name} ({typ}): {str(e)[:60]}"
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(poll, boards.items()))
    ok = sum(1 for _, e in results if not e); board_posts = [p for r, _ in results for p in r]
    errors += [e for _, e in results if e]; postings += board_posts
    report.append(f"company boards {ok}/{len(boards)} ok ({len(board_posts)} internships)"); report.append(f"{len(covered)}/{len(comps)} watchlist companies tracked directly")
    for fn, label, needs in ((S.adzuna, "Adzuna", "ADZUNA_APP_ID"), (S.jsearch, "JSearch", "RAPIDAPI_KEY")):
        if not os.environ.get(needs): report.append(f"{label} off"); continue
        if label == "Adzuna" and os.environ.get("RUN_ADZUNA", "1") != "1": continue
        try: got = fn(); postings += got; report.append(f"{label} {len(got)}")
        except Exception as e: errors.append(f"{label}: {str(e)[:80]}"); report.append(f"{label} error")

    alerts, new_jobs, held, run_urls = [], [], 0, set()
    for p in postings:
        if not p["url"] or not p["title"] or p["id"] in seen or p["url"] in seen_urls or p["url"] in run_urls: continue
        tkey = key(p["company"]) + "|" + p["title"].lower().strip()
        if tkey in seen_titles: continue
        posted = norm_posted(p["posted"])
        if p["board"]: seen[p["id"]] = now
        sc, why = score(p)
        if sc < C.MIN_SCORE: continue
        c = resolve(p["company"])
        if c: st, ev, tag = status[c["name"]][0], status[c["name"]][1], "watchlist"
        elif employers:
            m = employers.match([p["company"]]); st = classify(m)
            if st != "Sponsors in your field": continue
            ev, tag = evidence(m), "new-company"
        else: held += 1; continue
        seen[p["id"]] = now; seen_titles.add(tkey); run_urls.add(p["url"])
        fresh = (now - posted <= C.MAX_AGE_HOURS * 3600) if posted else (p["board"] in known_boards)
        job = dict(id=p["id"], company=p["company"], title=p["title"], location=p["location"], url=p["url"], score=sc, why=why,
                   status=st, evidence=ev, tag=tag, source=p["source"], first_seen=today, found_at=now, posted=posted, fresh=fresh, applied=False)
        new_jobs.append(job)
        if fresh: alerts.append(job)

    # Simplify/Adzuna/JSearch timestamps can be wrong (re-listed old jobs), so check the employer's own page before alerting
    DIRECT = {"Greenhouse", "Lever", "Ashby", "Smartrecruiters", "Workday"}; cut = dt.datetime.fromtimestamp(now - C.MAX_AGE_HOURS * 3600, dt.timezone.utc).date(); kept = []
    for a in alerts:
        if a["source"] in DIRECT: kept.append(a); continue
        real = S.verify_age(a["url"])
        if real:
            a["posted"] = dt.datetime(real.year, real.month, real.day, tzinfo=dt.timezone.utc).timestamp(); a["posted_exact"] = False
            if real >= cut: kept.append(a)                    # page confirms it is recent
            else: a["fresh"] = False                          # page says it is old: keep on dashboard, no alert
        elif a["source"].startswith("Simplify"): a["fresh"] = False   # Simplify's own time can't be trusted and the page has no date
        else: a["unverified"] = True; kept.append(a)
    alerts = kept
    for j in jobs:                                           # an alert stops being 'new' after its scan
        if j.get("fresh"): j["fresh"] = False

    # save state + dashboard data
    state = {"seen": {k: v for k, v in seen.items() if now - v < 150 * 86400},
             "boards": sorted(known_boards | {f"{key(n)}|{t}" for (t, _, _), n in boards.items()})}
    # dashboard = today's jobs only (Eastern day). Anything from an earlier day is deleted, except jobs found in the last 8 hours
    # (so a job posted at 11pm is still there at 5am). Old/unconfirmed jobs that failed the age check never reach the dashboard.
    day = prev_day if prev_day.get("date") == today else {"date": today, "pulled": 0, "skipped_old": 0}
    day["pulled"] += len(alerts); day["skipped_old"] += max(0, len(new_jobs) - len(alerts)); state["day"] = day
    jsave("state.json", state, separators=(",", ":"))
    keep = lambda j: j.get("found_at") and (j.get("first_seen") == today or now - j["found_at"] < C.MAX_AGE_HOURS * 3600)
    jobs = alerts + [j for j in jobs if keep(j) and j["id"] not in {a["id"] for a in alerts}]
    jsave("jobs.json", jobs, separators=(",", ":"))
    jsave("meta.json", {"last_run": dt.datetime.now(dt.timezone.utc).isoformat(), "scanned": len(postings), "new": len(new_jobs), "alerts": len(alerts),
                        "today": day, "sources": report, "sponsor_data": bool(employers), "untracked": missing})

    status_line = html.escape(" · ".join(report))
    notes = ""
    if not employers: notes += "\n⚠️ Sponsor data not loaded: only your watchlist companies are shown, marked unverified" + (f"; {held} other jobs held back." if held else ".")
    if len(errors) > max(5, len(boards) // 4): notes += f"\n⚠️ {len(errors)} sources failed (e.g. {html.escape(errors[0])})"
    if not alerts:
        if os.environ.get("HEARTBEAT") == "1" or notes:   # hourly scans stay silent unless something is wrong; one daily check-in
            telegram(f"InternFlow: no new matching internships this scan. {max(0, len(new_jobs) - len(alerts))} older or unconfirmed postings skipped.\n<i>{status_line}</i>{notes}")
    else:
        alerts.sort(key=lambda a: -a["score"]); shown = alerts[:C.MAX_ALERTS_PER_RUN]
        head = f"<b>InternFlow: {len(alerts)} new internship{'s' if len(alerts) != 1 else ''}</b>"
        msg = head
        for a in shown:
            if a.get("posted_exact") is False: ago = f"posted {dt.datetime.fromtimestamp(a['posted'], dt.timezone.utc).strftime('%b %d')} (per job page) · "
            elif a.get("unverified"): ago = "age not confirmed on job page · "
            elif a["posted"]: ago = f"posted {max(1, int((now - a['posted']) / 3600))}h ago · "
            else: ago = "just appeared · "
            blk = (f"\n\n{'🆕 NEW COMPANY · ' if a['tag'] == 'new-company' else '⭐ '}<b>{html.escape(a['title'])}</b>\n"
                   f"{ago}{html.escape(a['company'])} · {html.escape(a['location'] or 'n/a')} · {html.escape(a['source'])}\n"
                   f"{BADGE.get(a['status'], '⚠️')} {html.escape(a['status'])}: {html.escape(a['evidence'][:150])}\n"
                   f"Fit {a['score']}/100 · {html.escape('; '.join(a['why']) or 'general match')}\n"
                   f"<a href=\"{html.escape(a['url'], quote=True)}\">Open job</a>")
            if len(msg) + len(blk) > 3800: telegram(msg); msg = "<b>InternFlow (continued)</b>"
            msg += blk
        if len(alerts) > len(shown): msg += f"\n\n…{len(alerts) - len(shown)} more on your dashboard"
        telegram(msg + f"\n\n<i>{status_line}</i>{notes}")
        if C.AUTO_TAILOR:
            try:
                import tailor
                picks = [a["url"] for a in alerts if a["score"] >= C.AUTO_TAILOR_MIN_SCORE][:C.AUTO_TAILOR_MAX_PER_RUN]
                if picks: tailor.tailor_urls(picks, {j["url"]: j for j in alerts}, auto=True)
            except Exception as e: print("auto-tailor skipped:", e)
    print("done", report, "errors:", errors[:10])

if __name__ == "__main__":
    if os.environ.get("TEST") == "1": telegram("✅ InternFlow is connected. Scans run every hour from 6am to 10pm Eastern and message you here when something new and fresh appears."); raise SystemExit
    try: run()
    except Exception as e:
        telegram(f"❌ InternFlow scan failed: {html.escape(str(e)[:300])}"); traceback.print_exc(); raise
