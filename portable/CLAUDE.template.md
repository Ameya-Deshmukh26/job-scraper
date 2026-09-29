# Job Scout: instructions for Claude

This folder is **Job Scout**, a personal job-search dashboard. It checks job
sites and company career pages every few hours, keeps only the jobs that fit
the user, scores each one, and shows them in a web page at
http://localhost:5000.

The person using this folder is **probably not technical**. They may never
have used a terminal. You do every technical step yourself. They should only
ever answer questions, click buttons in the dashboard, and paste API keys.

## How to talk to them

- Plain, friendly language. No jargon: say "job sites", not "sources";
  "settings", not "config"; "the dashboard", not "the Flask app".
- One question at a time. Use the AskUserQuestion tool with choices whenever
  the answer has common options (roles, cities, experience).
- Before each technical step, say in one short line what you are doing and
  why ("Installing the tools the dashboard needs, about 2 minutes").
- Never ask them to open or edit a code file. You edit files; they answer.
- If something fails, fix it yourself. Only involve them when you truly need
  something from them (a decision, a key, installing Python).

## First run

`search_profile.py` ships with a **starter search** already filled in:
MBA-track roles (Associate Product Manager, Product Manager, Business
Analyst, Strategy Associate, Management Consultant, Product Marketing, Brand
and Category Manager, Founder's Office, Program Manager) anywhere in India,
for someone with 0-3 years of experience. It works without any changes.

If `SETUP_DONE = False`, run **Setup** below as soon as they say anything
("hi", "start", "set me up", or a question), after explaining in two lines
what you are about to do. Setup installs everything, then personalises the
starter search. If they just want to get going, install, keep the starter
search as it is, and open the dashboard. They can personalise it any time.

## Setup

### 1. Welcome (short)

Explain what Job Scout does in 4-5 short bullets:

- Searches LinkedIn, company career pages (Amazon, Stripe, OpenAI and a few
  hundred others) and startup job boards for them, every few hours.
- Keeps only jobs matching their roles, cities and experience level, and
  hides ones asking for too many years of experience.
- Gives every job a match score so the best ones are at the top.
- Everything runs on their own computer. Their data is not sent anywhere.
- Optional extras (Google Jobs, Indeed) need a free or cheap API key, which
  you explain at the end.

Then say setup takes about 10 minutes: a few questions, then you install
everything and open the dashboard.

### 2. Check Python

Run `python --version` (on Mac: `python3 --version`). It needs Python 3.10 or
newer. If it is missing:

- **Windows:** ask them to download Python from https://www.python.org/downloads/
  and, in the installer, **tick "Add python.exe to PATH"** before clicking
  Install. Then they must close and reopen Claude Code so it sees Python.
- **Mac:** same download page, run the installer.

Use `python3` everywhere below if that is what works on their machine.

### 3. Install (do this while asking the questions, if you can)

```
python -m pip install -r requirements.txt
python -m playwright install chromium
```

The second command downloads a browser used by one job site (HiringCafe). If
it fails, carry on: everything else still works.

### 4. Personalise the starter search

First read the starter search back to them in 3-4 lines (roles, "anywhere in
India", 0-3 years of experience) and ask whether to keep it or adjust it. If
they keep it, only ask for their name and go to step 5.

To adjust, ask these one at a time, **starting from what is already in
`search_profile.py`**: show the current values as the suggested choices so
they only change what they want. Do not make them type long lists.

1. **Their name** (shown on the dashboard).
2. **Background**: degree and specialisation (e.g. MBA Marketing), college,
   graduation year, years of work experience and in what. Write 1-2 plain
   sentences of facts into `CANDIDATE_SUMMARY`.
3. **Roles** (multi-select). Common MBA-track options: Product Management,
   Strategy / Consulting, Business or Data Analytics, Marketing / Brand,
   Finance / Corporate Finance, Operations / Supply Chain, Sales / Business
   Development, Founder's Office / General Management, HR / People.
   Then turn their picks into:
   - `SEARCH_TITLES`: 6-10 concrete titles people actually post, e.g.
     "Associate Product Manager", "Product Manager", "Business Analyst",
     "Strategy Associate", "Management Consultant", "Founder's Office",
     "Brand Manager", "Category Manager", "Financial Analyst",
     "Program Manager". Show them the list and let them add or remove.
   - `KEYWORDS`: shorter lowercase phrases that catch variants, e.g.
     "product manager", "product analyst", "business analyst", "strategy",
     "consultant", "brand", "category manager", "founder's office",
     "financial analyst", "program manager". A title must contain one of
     these to be kept, so do not leave out anything they want.
   - `RANK_TOP_TITLES`: the 2-4 roles they want most (lowercase).
     `RANK_GOOD_TITLES`: the rest (lowercase).
   - `RANK_BONUS_WORDS`: a few lowercase words from their strongest
     experience or interests (e.g. "fintech", "growth", "d2c", "saas").
4. **Experience level.** Ask how many years of full-time work they have.
   Set `MAX_YEARS_REQUIRED` to about their years + 3 (fresh MBA with 0-2
   years: 4; 3-5 years: 7). Keep `EXCLUDE_SENIOR = True` unless they have
   6+ years.
5. **Country** (default India) and **cities** (multi-select): Bengaluru,
   Mumbai, Delhi NCR, Pune, Hyderabad, Chennai, Kolkata, Ahmedabad, Remote.
   Then set:
   - `SEARCH_COUNTRY`: exactly as spelled in `COUNTRIES` in config.py.
   - `LOCATION_FILTER`: lowercase, **with spelling variants**. For India:
     `"bengaluru", "bangalore"` / `"mumbai", "navi mumbai", "bombay"` /
     `"delhi", "new delhi", "gurugram", "gurgaon", "noida", "ncr"` /
     `"pune"` / `"hyderabad"` / `"chennai"` / `"kolkata"`. Add `"india"`
     only if they are open to anywhere in India. For remote, add
     `"remote, india"` and `"india (remote)"` rather than a bare
     `"remote"`, which would also let in US-only remote jobs.
   - `PREFERRED_LOCATIONS`: their first-choice city (both spellings).
   - `SEARCH_CITIES`: their top 1-2 cities, formatted like
     "Bengaluru, Karnataka" (only used by the paid Indeed search).
6. **Visa.** Only if they want jobs in the US: do they need H-1B
   sponsorship? If yes set `NEEDS_SPONSORSHIP = True`. For a search in
   India leave it False and leave `US_ONLY = False`.
7. **Dream companies** (optional). For each company they name, check
   whether it has a public job board and add it to the matching list in
   config.py:
   - Greenhouse: `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs`
     returns JSON -> add `<slug>` to `GREENHOUSE_COMPANIES`
   - Lever: `https://api.lever.co/v0/postings/<slug>?mode=json` returns a
     list -> add to `LEVER_COMPANIES`
   - Ashby: `https://jobs.ashbyhq.com/<slug>` loads -> add to `ASHBY_COMPANIES`
   Tell them which ones you could add and which have no public board
   (LinkedIn and Google Jobs still cover those).

### 5. Save

Write the answers into `search_profile.py` and set `SETUP_DONE = True`.
Check it loads: `python -c "import config; print(config.SEARCH_TITLES)"`.
Read the list back to them in one or two lines.

**Level exclusions for MBA roles:** `EXCLUDE_LEVELS` must not contain a bare
`"manager"`. That would drop Product Manager, Brand Manager, Category Manager
and most MBA-track titles. Exclude only "senior manager", "general manager",
director, head of, VP, chief, principal, partner.

### 6. Start the dashboard

Start it in the background: `python app.py` (Windows users can also
double-click `start.bat` later). If port 5000 is busy, use
`python app.py --port 5050` and use that port below. Open
http://localhost:5000 for them (use the preview tool, or tell them to open it
in their browser).

Kick off a first search: set "Lookback hrs" to 24 and click **Scan LinkedIn**
on the LinkedIn tab, or run it yourself:

```
curl -X POST localhost:5000/api/group-scan/linkedin -H "Content-Type: application/json" -d "{\"hours\": 24}"
```

The other groups are `boards` and `big` (Workday + Google Jobs + Indeed; add
`"paid": true` to include the paid two). Progress:
`GET localhost:5000/api/group-scan/status`.

A scan of the Boards tab and of Workday also starts by itself when the
dashboard opens, then every hour. It takes a few minutes; the buttons show
progress.

Then show them around in plain words. There are four tabs, each with one
Scan button:

- **All**: every matching job, best match first. The number on each card is
  the match score out of 100. **Scan everything** runs every tab's scan.
- **LinkedIn**: LinkedIn jobs only.
- **Boards**: company career pages (Amazon, Stripe, OpenAI and a few hundred
  others), startup boards and Hacker News.
- **Workday + Google**: big-company Workday sites, plus Google Jobs and
  Indeed if they have keys. It asks before spending credits.
- **Apply** opens the real job posting. The bookmark marks it applied, so it
  hides from the list.
- **Agent Rank**: asks the AI to re-rank the top jobs with a one-line reason
  for each. It uses their Claude Code login, so there is no extra cost.
- **Lookback hrs**: how far back each scan looks.
- The tiles on each tab show, per job site, how many jobs the last scan
  found and how long it took.

### 7. Optional extras (explain, do not push)

Two job sites need a paid service to reach. Both are optional.

| Extra | What it adds | Cost | Where to get a key |
|---|---|---|---|
| **Google Jobs** (SerpApi) | Google's job search. In India this pulls in Naukri, foundit, Instahyre and company career pages, so it is the most useful extra. | Free plan with a monthly search allowance; each Google Jobs run uses up to 8 searches | https://serpapi.com, sign up, then Dashboard, then "Your Private API Key" |
| **Indeed** (Firecrawl) | Indeed India listings | Free trial credits, then paid; each run uses up to 6 | https://firecrawl.dev, sign up, then API Keys |

How the key gets in:

- The keys live in the file `.env` in this folder, one per line, e.g.
  `SERPAPI_API_KEY=abc123`. Open `.env` for them and ask them to paste the
  key after the `=` and save.
- If that is too fiddly, they can paste the key into this chat and you write
  it into `.env` yourself. Do not repeat the key back, and never put it in
  any other file.
- Google Jobs picks the key up immediately. For Indeed, restart the
  dashboard after adding the key.
- Then **Scan** on the Workday + Google tab (and **Scan everything**) can
  include them. It asks each time before spending credits.

### 8. Optional: resume tailoring

The dashboard can rewrite resume bullets for a specific job (the sparkle
button on each card). It needs their resume as `resume.tex` in this folder,
in LaTeX with each bullet as `\resumeItem{...}` and each role as
`\resumeSubheading{Company}{Dates}{Title}{Location}`.

If they want it, ask for their resume (PDF or Word; they can drag it into
the chat), and write `resume.tex` from it:

- Use **only** what is in their resume. Do not add, improve or invent
  anything. The tailoring checker rejects any claim, number or skill that is
  not in this file, so an invented detail would get used later.
- Keep sections as `\section{Experience}`, `\section{Education}`,
  `\section{Projects}`, `\section{Skills}`, and define the two macros in the
  preamble.
- Check it parses: `python -c "from agent.corpus import load_corpus; print(len(load_corpus()))"`
  should print a number above 0.

Tailored files are saved in the `resumes` folder. Turning them into PDFs
needs a LaTeX install (MiKTeX on Windows); without it they get the `.tex`
file, which they can upload to https://overleaf.com to make a PDF.

## Everyday use

- "Find me jobs" / "anything new?": run a LinkedIn scan (and Google Jobs if
  they have a key), then read `http://localhost:5000/api/jobs`. Summarise the
  top 5-10 by match score, with title, company, city and link.
- "Change my search" / "add Pune" / "I also want marketing roles": edit
  `search_profile.py`, then restart the dashboard so it takes effect.
- "Tailor my resume for <job>": use the sparkle button's endpoint
  `POST /api/agent/tailor/<job_id>`, or guide them to click it.
- "Open the dashboard": start `python app.py` if it is not running, then
  open http://localhost:5000.

## Do not

- Turn on `ENABLE_AUTO_APPLY` or use the auto-apply code. It submits real
  applications with no review.
- Apply to jobs, send emails or messages, or create accounts for them.
- Share, print, upload or commit `.env`. It holds their keys.
- Invent anything in their resume or profile.

## Troubleshooting

- **No jobs showing:** usually `KEYWORDS` or `LOCATION_FILTER` is too
  narrow. Check `job_scraper.log`, loosen the filters, restart, rescan.
- **"Starter search" banner still showing:** `SETUP_DONE` is not True, or
  the dashboard was not restarted after saving.
- **LinkedIn returns nothing / HTTP 429:** LinkedIn is rate-limiting. Wait
  15-30 minutes. The company-page and Google searches are unaffected.
- **Port 5000 in use:** `python app.py --port 5050`.
- **Mac:** use `python3` instead of `python`. Desktop notifications may not
  appear; that is fine.

## Where things are

- `search_profile.py`: everything about the person and their search
- `config.py`: company career-page lists, countries, scan timing
- `.env`: API keys (private)
- `app.py`: the dashboard. `main.py`: the scan engine, also runnable as
  `python main.py --hours 24` for a scan without the dashboard
- `sources/`: one file per job site
- `seen_jobs.db`: every job found, created on first run
- `resumes/`: tailored resumes
