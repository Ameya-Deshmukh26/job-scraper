# Job Scout

A job-search dashboard that runs on your own computer. It checks LinkedIn,
company career pages and startup job boards for you, keeps only the jobs that
fit you, and ranks them best first.

It comes set up for MBA roles in India: product management, strategy,
consulting, brand, category and business analyst jobs in Bengaluru, Mumbai,
Delhi NCR, Pune, Hyderabad, Chennai and the rest of India, for 0-3 years of
experience. You can change any of that just by telling Claude.

You don't need to know any coding. Claude Code does the setup with you.

## Setting it up (about 10 minutes, once)

1. **Unzip this folder** somewhere easy to find, like Documents.
2. **Install Python** if you haven't already: https://www.python.org/downloads/
   On Windows, **tick "Add python.exe to PATH"** at the bottom of the first
   installer screen before clicking Install.
3. **Open this folder in Claude Code.**
   - Desktop app: choose "Open folder" and pick the `JobScout` folder.
   - Or in a terminal: go into the folder and type `claude`.
4. **Type: `set me up`**

Claude will explain what the tool does, install everything, show you the
starter MBA search, and ask if you want to adjust it (your cities, your
experience, the roles you want). Then it opens your dashboard.

## Using it

- **Open the dashboard:** double-click `start.bat` (Windows), or tell Claude
  "open the job board". It opens at http://localhost:5000
- **Search again:** each tab has a **Scan** button, and **Scan everything** on
  the All tab runs them all.
- **Change what you're looking for:** just tell Claude, e.g. "add Pune" or
  "I also want marketing roles".
- **Ask Claude anything:** "anything new today?", "what are my best
  matches?", "tailor my resume for this job".

## Optional extras

Google Jobs and Indeed need an API key from a paid service (both have a free
tier or trial). Ask Claude "how do I add Google Jobs?" and it will walk you
through it. Your keys stay in the `.env` file on your computer. Don't share
that file.

## Privacy

Everything runs on your computer. Your searches, saved jobs and keys are not
sent anywhere except to the job sites being searched.
