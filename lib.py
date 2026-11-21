"""Shared helpers: name matching, Telegram, JSON files."""
import os, re, json, time, requests
from pathlib import Path
ROOT = Path(__file__).resolve().parent
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", ""); TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

_FILLER = {"inc","incorporated","llc","llp","lp","corp","corporation","company","co","ltd","limited","na","n","a","plc","us","usa","the","and","of"}
DENY_EXTRA = {"bank","bancorp","savings","credit","union","hospital","hospitals","university","college","school","church","county","city",
              "foundation","clinic","realty","restaurant","restaurants","insurance","capital","partners","ventures"}

def tokens(name):
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " and ")); t = s.split()
    return [x for x in t if x not in _FILLER] or t
def key(name): return " ".join(tokens(name))

def name_matches(short, full, max_extra=2):
    """short/full are token lists. True if `full` is `short` plus at most a few harmless words
    ('Nissan' ~ 'Nissan Global', 'Flowserve' ~ 'Flowserve US Inc'), never 'Apple' ~ 'Apple Bank'."""
    if not short or full[:len(short)] != short: return False
    extra = full[len(short):]
    return len(extra) <= max_extra and not (set(extra) & DENY_EXTRA)

def jload(name, default):
    try: return json.load(open(ROOT / name))
    except Exception: return default
def jsave(name, obj, **kw): json.dump(obj, open(ROOT / name, "w"), **kw)

def get_json(url, **kw):
    r = requests.get(url, timeout=40, headers=UA, **kw); r.raise_for_status(); return r.json()

def telegram(text):
    if DRY_RUN or not (TG_TOKEN and TG_CHAT):
        print("---- TELEGRAM (not sent) ----\n" + text + "\n"); return
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", timeout=30, json={
        "chat_id": TG_CHAT, "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True})
    if r.status_code != 200: raise RuntimeError(f"Telegram error {r.status_code}: {r.text[:200]}")
