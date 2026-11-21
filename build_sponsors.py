"""Builds employers.json (who sponsors H-1B / PERM, and in your field) from the free DOL disclosure files.

EASIEST (once, on your computer):  download the LCA and PERM .xlsx files from
  https://www.dol.gov/agencies/eta/foreign-labor/performance   (last 2 fiscal years of each, "Disclosure Data")
then run:   pip install openpyxl requests
            python build_sponsors.py LCA_Disclosure_Data_FY2026_Q3.xlsx PERM_Disclosure_Data_FY2026_Q3.xlsx ...
and upload the small employers.json it creates to your GitHub repo. (File names containing "PERM" are treated as PERM.)

AUTOMATIC (GitHub Actions, only if employers.json is missing):  python build_sponsors.py --auto   (best effort; DOL may block bots)
"""
import sys, re, os, json, requests
from collections import defaultdict
from pathlib import Path
from openpyxl import load_workbook
from lib import key, UA, ROOT, telegram
import config as C

NAME = ["EMPLOYER_NAME", "EMPLOYER_BUSINESS_NAME", "EMP_BUSINESS_NAME"]
SOC = ["SOC_CODE", "PW_SOC_CODE", "JOB_INFO_SOC_CODE", "PWD_SOC_CODE", "PW_SOC_CODE_1"]
STAT = ["CASE_STATUS", "CASE_STATUS_DESC"]
PAGE = "https://www.dol.gov/agencies/eta/foreign-labor/performance"

def pick(header, options, label, path):
    up = {str(h).strip().upper(): i for i, h in enumerate(header) if h}
    for o in options:
        if o in up: return up[o]
    raise SystemExit(f"{path}: no {label} column. Header starts: {list(header)[:30]}")

SEEN_CASES = set()          # a case can appear in more than one downloaded file; count it once
def aggregate(path, kind, stats):
    ws = load_workbook(path, read_only=True, data_only=True).active; it = ws.iter_rows(values_only=True); header = next(it)
    n, s, st = pick(header, NAME, "employer name", path), pick(header, SOC, "SOC code", path), pick(header, STAT, "case status", path)
    ci = next((i for i, h in enumerate(header) if str(h).strip().upper() == "CASE_NUMBER"), None)
    cnt = skipped = 0
    for r in it:
        if not str(r[st] or "").upper().startswith("CERTIFIED"): continue
        if ci is not None and r[ci]:
            if r[ci] in SEEN_CASES: skipped += 1; continue
            SEEN_CASES.add(r[ci])
        k = key(str(r[n] or ""))
        if not k: continue
        d = stats[k]; d["name"] = d["name"] or str(r[n]); d[kind] += 1; cnt += 1
        if any(str(r[s] or "").startswith(p) for p in C.FIELD_SOC_PREFIXES): d[kind + "_f"] += 1
    print(f"{Path(path).name}: {cnt:,} certified cases counted" + (f" ({skipped:,} repeats skipped)" if skipped else ""))

def auto_download(dest):
    html = requests.get(PAGE, headers=UA, timeout=60).text
    links = sorted(set(re.findall(r'href="([^"]+\.xlsx)"', html, re.I)))
    urls = []
    for kind in ("lca_disclosure", "perm_disclosure"):
        c = [l for l in links if kind in l.lower()]
        c.sort(key=lambda l: (re.findall(r"FY(\d{4})", l, re.I) or ["0"])[0] + (re.findall(r"Q(\d)", l, re.I) or ["9"])[0], reverse=True)
        urls += c[:2]
    if not urls: raise SystemExit("could not find DOL file links on the page")
    out = []
    for u in urls:
        u = "https://www.dol.gov" + u if u.startswith("/") else u; f = dest / u.split("/")[-1].split("?")[0]
        with requests.get(u, headers=UA, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(f, "wb") as fh:
                for ch in r.iter_content(1 << 20): fh.write(ch)
        out.append(str(f))
    return out

def main(files):
    stats = defaultdict(lambda: dict(name="", lca=0, lca_f=0, perm=0, perm_f=0))
    for f in files: aggregate(f, "perm" if "perm" in Path(f).name.lower() else "lca", stats)
    rows = [[k, v["name"], v["lca"], v["lca_f"], v["perm"], v["perm_f"]] for k, v in stats.items() if v["lca_f"] + v["perm_f"] > 0 or v["lca"] + v["perm"] >= 10]
    json.dump(rows, open(ROOT / "employers.json", "w"), separators=(",", ":"))
    print(f"employers.json written: {len(rows):,} employers ({os.path.getsize(ROOT / 'employers.json') / 1e6:.1f} MB)")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: raise SystemExit(__doc__)
    if a == ["--auto"]:
        try:
            tmp = Path("/tmp/dol"); tmp.mkdir(exist_ok=True); main(auto_download(tmp))
            telegram("📊 InternFlow: sponsor data built from DOL files.")
        except BaseException as e:
            telegram(f"⚠️ InternFlow could not download DOL sponsor data automatically ({str(e)[:150]}). Build employers.json on your computer: see README step 6.")
            raise SystemExit(0)
    else: main(a)
