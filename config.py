"""EDIT THIS FILE to change what you want. Everything is plain lists."""
# --- freshness / volume ---
MAX_AGE_HOURS = 8           # a posting counts as "new" (Telegram alert) if posted within this many hours (jobs with no timestamp count if first seen this scan)
MIN_SCORE = 24              # lower = more jobs (volume), higher = stricter. 24 is broad, 40 is strict
MAX_ALERTS_PER_RUN = 60     # Telegram shows at most this many per run; the rest are on the dashboard
TERMS = {"Spring 2027", "Summer 2027", "Fall 2027"}     # Simplify feed seasons to keep
ADZUNA_MAX_AGE_DAYS = 2

# What to search on job-board aggregators (Adzuna + JSearch)
SEARCHES = ["supply chain intern", "procurement intern", "supply chain data analyst intern", "business analyst intern", "operations research intern",
            "data analyst intern", "operations analyst intern", "logistics intern", "business intelligence intern",
            "sourcing intern", "analytics intern", "operations intern", "planning intern", "co-op supply chain",
            "demand planning intern", "inventory analyst intern", "ERP analyst intern", "business systems analyst intern",
            "transportation analyst intern", "supply planner intern", "strategy analyst intern", "consulting analyst intern",
            "S&OP intern", "category analyst intern", "global supply intern", "supply chain systems intern", "network optimization intern",
            "decision science intern", "purchasing intern"]

# --- "my field" in DOL H-1B / PERM data (SOC code prefixes) ---
FIELD_SOC_PREFIXES = ["13-1081", "13-1023", "13-1022", "13-1111", "13-1161", "13-1199", "13-1051",
                      "15-2031", "15-2051", "15-2041", "15-1211", "11-3071", "11-3061"]
# companies NOT on your watchlist are only shown if DOL data shows this many certified cases in your field
MIN_FIELD_CASES_NEW_COMPANY = 3

# --- title scoring (points) ---
TITLE_KEYWORDS = {
    "supply chain": 30, "procurement": 30, "purchasing": 28, "sourcing": 26, "logistics": 24, "operations analyst": 26,
    "business analyst": 28, "business analytics": 28, "data analyst": 22, "business intelligence": 24, "analytics": 16,
    "planning": 14, "demand": 14, "inventory": 14, "sap": 18, "erp": 18, "consulting": 14, "advisory": 12,
    "operations": 10, "category management": 20, "buyer": 18, "analyst": 14, "reporting": 12, "strategy": 10,
    "project management": 12, "transportation": 16, "warehouse": 14, "fulfillment": 14, "vendor": 14, "supplier": 14,
    "pricing": 10, "forecast": 12, "business operations": 16, "process improvement": 14, "continuous improvement": 12,
    "data": 10, "manufacturing": 8, "lean": 8,
    # from your target-title list
    "operations research": 28, "decision science": 22, "network optimization": 24, "demand planning": 28, "supply planning": 26,
    "supply planner": 26, "s&op": 24, "mrp": 20, "material": 12, "category analyst": 22, "global supply": 22, "supply management": 24,
    "supply chain systems": 24, "systems analyst": 18, "business systems": 22, "data scientist": 16, "bi engineer": 22,
    "business intelligence engineer": 24, "program manager": 12, "kinaxis": 14, "optimization": 14,
}
# skills from your background; found in title/description -> shown as "why it fits"
PROFILE_SKILLS = {
    "sap": ("SAP", 8), "excel": ("Excel", 4), "vba": ("Excel VBA", 8), "power bi": ("Power BI", 6), "tableau": ("Tableau", 5),
    "sql": ("SQL", 6), "python": ("Python", 5), "dashboard": ("dashboards", 4), "procurement": ("procurement", 8),
    "requisition": ("requisitions", 6), "supply chain": ("supply chain", 8), "automation": ("automation", 4),
}
BAD_TITLE = ["software engineer", "swe", "machine learning engineer", "phd", "mba", "firmware", "mechanical", "electrical",
             "chemical engineer", "nurse", "frontend", "backend", "full stack", "full-stack", "devops", "quant", "hardware engineer"]

# --- automatic tailoring (needs the ANTHROPIC_API_KEY and MASTER_RESUME secrets; off if they are missing) ---
AUTO_TAILOR = True
AUTO_TAILOR_MIN_SCORE = 55      # only jobs that fit this well get a resume + cover letter sent automatically
AUTO_TAILOR_MAX_PER_RUN = 4     # keeps API cost small
APPLY_GOAL = 1000
APPLY_DEADLINE = "2027-03-20"   # the date you want 1000 applications done by
