"""Records one application sent from your phone or laptop (by autofill.user.js) into applied.json, then confirms on Telegram."""
import os, re, json, html, datetime as dt
from urllib.parse import urlsplit
from lib import *
import config as C

def nurl(u):
    p = urlsplit(u or ""); path = re.sub(r"/(apply|application)(/.*)?$", "", p.path.rstrip("/"), flags=re.I)   # apply pages -> the job page
    return (p.netloc.lower() + path).lower()

def main():
    try: ev = json.loads(os.environ.get("PAYLOAD", "{}"))
    except Exception: ev = {}
    url = (ev.get("url") or "").strip()
    if not url.startswith("http"): print("no url, ignoring"); return
    applied = jload("applied.json", [])
    if any(nurl(a["url"]) == nurl(url) for a in applied): print("already tracked"); return
    jobs = jload("jobs.json", []); m = next((j for j in jobs if nurl(j["url"]) == nurl(url)), None)
    if not m and ev.get("company"):   # fall back to company + title
        m = next((j for j in jobs if key(j["company"]) == key(ev["company"]) and key(j["title"]) == key(ev.get("title", ""))), None)
    rec = dict(url=m["url"] if m else url, job_id=m["id"] if m else None,
               company=(m or {}).get("company") or ev.get("company") or urlsplit(url).netloc,
               title=(m or {}).get("title") or ev.get("title") or "Application",
               at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), device=str(ev.get("device", ""))[:30])
    applied.append(rec); jsave("applied.json", applied, separators=(",", ":"))
    n = len(applied); today = dt.date.today(); week = sum(1 for a in applied if (today - dt.date.fromisoformat(a["at"][:10])).days < 7)
    left = max(1, (dt.date.fromisoformat(C.APPLY_DEADLINE) - today).days); need = max(0, C.APPLY_GOAL - n)
    telegram(f"✅ <b>Applied #{n}</b>: {html.escape(rec['title'])} · {html.escape(rec['company'])}\n"
             f"{n}/{C.APPLY_GOAL} · {week} in the last 7 days · about {-(-need // left)}/day needed to reach {C.APPLY_GOAL} by {C.APPLY_DEADLINE}")

if __name__ == "__main__": main()
