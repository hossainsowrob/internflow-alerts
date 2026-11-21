# InternFlow v4: find fresh internships -> Telegram alert -> autofill -> tailored resume/cover letter

Pipeline:  scanner every hour (GitHub, free) -> Telegram alert (+ auto-tailored resume and cover letter for the best fits)
-> you tap the job link -> autofill script fills your details (phone or laptop) -> you finish and press Submit
-> the script logs it -> Telegram says "Applied #N" -> dashboard shows progress toward 1000.

## 1. Alerts (every hour, 6am to 10pm Eastern; only jobs posted in the last 8 hours)
Freshness: a job alerts if its own timestamp is within 8 hours, or, when the site gives no timestamp (some company boards),
if it first appeared since the previous hourly scan. Direct company boards are the fastest. Simplify, Adzuna and JSearch lag the
original post, so some of their jobs are older than 4 hours when you see them. GitHub can start scheduled runs 5-30 minutes late.
Quiet hours: no scan 10pm-6am. Hourly scans stay silent when nothing is new; you get one check-in message at 7am.
Use a PUBLIC repo (unlimited free Actions minutes). A private repo has 2,000 free minutes a month, which hourly scans can use up.
Sources: SimplifyJobs, each company's own Workday/Greenhouse/Lever/Ashby/SmartRecruiters board, Adzuna and JSearch (optional keys).
Companies in companies.csv always show; other companies show only if DOL data proves H-1B/PERM filings in your field.
Tracking each of your companies directly: `discover.py` runs weekly and finds boards it can (Greenhouse, Lever, Ashby, Workday guesses,
SmartRecruiters). For a company it can't find, paste its careers link into companies.csv (column career_url) if it is Workday /
Greenhouse / Lever / Ashby / SmartRecruiters. Companies on iCIMS, Oracle, SuccessFactors, Taleo or their own site cannot be read
directly; they only appear through Simplify / Adzuna / JSearch, usually later. Each scan reports how many of your companies are tracked.

### Setup
1. New public GitHub repo. Upload every file from this folder except scan.yml, tailor.yml and track.yml (and keep the `resume` folder). Include applied.json, manifest.webmanifest, sw.js and the two icon-*.png files.
2. Add file > Create new file, name `.github/workflows/scan.yml`, paste scan.yml, commit. Repeat for `.github/workflows/tailor.yml` and `.github/workflows/track.yml`.
3. Settings > Secrets and variables > Actions > secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
   Optional: ADZUNA_APP_ID, ADZUNA_APP_KEY (developer.adzuna.com, free), RAPIDAPI_KEY (JSearch on rapidapi.com).
4. Settings > Actions > General > Workflow permissions > Read and write.
5. Settings > Pages > main / (root). Dashboard: https://YOUR-USERNAME.github.io/REPO-NAME/
6. Sponsor data, once: download the LCA and PERM "Disclosure Data" .xlsx files (last 2 fiscal years) from
   https://www.dol.gov/agencies/eta/foreign-labor/performance, then on your computer:
   pip install openpyxl requests ; python build_sponsors.py LCA_xxx.xlsx PERM_xxx.xlsx ; upload the employers.json it makes.
7. Actions > InternFlow scan > Run workflow, first with "test" ticked, then unticked.

## 2. Autofill + tracking on phone and laptop (autofill.user.js, made for InternFlow)
It adds three buttons on application pages: ⚡ Fill, ✅ Applied, ⚙. It fills your name, contact, links, school, graduation,
location and similar fields, attaches your default resume, outlines required fields still empty in red, and stops. You finish
the rest and press Submit yourself. It never touches gender, race, veteran, disability, salary or date-of-birth fields.
Work-authorization and sponsorship questions are answered only if you fill those two settings; leave them blank to answer them yourself.
It works on: Greenhouse, Lever, Ashby, Workday, SmartRecruiters, iCIMS, Taleo, Oracle, SuccessFactors, Workable, Jobvite, BambooHR,
Breezy, Recruitee. Other sites: add a `// @match` line in the script header.
Limits: dropdowns built with custom widgets, free-text questions, and Workday account creation/sign-in are left to you.
Workday makes you create an account for each employer once.

Install once per device (your settings are stored per device):
- Laptop (Chrome, Edge or Firefox): install Tampermonkey. In Chrome: Extensions > Tampermonkey > Details > turn on "Allow user scripts".
  Open Tampermonkey > Create new script, delete the template, paste autofill.user.js, save.
- Android: Chrome has no extensions. Install Firefox, then the Violentmonkey add-on, then create a new script and paste autofill.user.js.
- iPhone: install the free "Userscripts" app from the App Store, enable it in Settings > Apps > Safari > Extensions, point it at a
  folder, and save autofill.user.js there. Use Safari.
- Telegram opens links in its own mini browser, where scripts cannot run. Turn that off: Telegram > Settings > Chat Settings >
  turn off "In-App Browser" (iPhone) or choose "Open in default browser" (Android). Then job links open in Firefox / Safari / Chrome.
- On the first page, tap ⚙ and enter only the tracking settings below. Your name, email, phone, links and resume are READ FROM YOUR
  PORTFOLIO (default https://hossainsowrob.github.io, re-read every 6 hours), so change your portfolio and the script follows.
  It finds: a mailto: link, a tel: link, LinkedIn and GitHub links, your name from the page heading, and a link to your resume
  PDF or Word file (a link whose text or address says resume or CV). Tap "Sync from portfolio now" to see what it read. For exact
  control, paste this into your portfolio HTML and fill it in (city, state, ZIP and address can only come from here):
  <script type="application/json" id="internflow-profile">{"first":"","last":"","email":"","phone":"","city":"","state":"","zip":""}</script>
  Anything you type in ⚙ overrides the portfolio. If the portfolio is built by JavaScript with no readable HTML, it can't be read.

Tracking: when you press Submit and the page shows its confirmation ("Thank you for applying"), the script logs the application.
If a site shows no confirmation, tap ✅ Applied yourself. The log is `applied.json` in your repo, and Telegram replies
"Applied #N, about X/day needed". Both phone and laptop write to the same log. The dashboard counts it.
To allow logging: GitHub > Settings > Developer settings > Fine-grained tokens > new token, only your InternFlow repo,
permission Contents: Read and write. Paste your username, repo name and token into ⚙. The token lives only on your devices.
Treat it like a password and delete it on GitHub if a device is lost.
Dashboard on your phone: open the Pages link, then "Add to Home Screen". It installs like an app.
The earlier option, AutoInternshipClaude (https://github.com/pqthangv/AutoInternshipClaude), is laptop-only and optional for complex forms.

## 3. Tailored resume + cover letter (optional, uses an Anthropic API key, costs a few cents per job; check current pricing)
8. The master resume is read live from your portfolio: the text of the resume PDF/Word file it links to (or the page text if there is no
   file). Only add the secret ANTHROPIC_API_KEY. Optional: a MASTER_RESUME secret overrides the portfolio.
9. Automatic: after each alert, jobs scoring 55+ get a tailored resume and cover letter sent to Telegram (up to 4 per scan; change in config.py).
   Manual: Dashboard > "Tailor resume" on a job (copies its link, opens the workflow page) > Run workflow > paste the link(s).
   Resume.docx and CoverLetter.docx arrive in Telegram. They use plain one-column Word formatting, which ATS software reads reliably.
   The tool only uses facts from your master resume and flags any number it can't find there. Read both and edit before sending.
Nothing can guarantee passing an ATS or an AI screen. This keeps formatting clean and wording truthful and specific.
