# Job Radar

A job feed that rebuilds itself every morning while you sleep.

It reads career pages directly from around 270 employers across genomics,
biotech, conservation, marine science, museums, science media, climate, public
health and policy, plus a set of open job feeds and conservation-specific
boards. Then it throws out anything senior, anything that is really a machine
learning engineering job, and anything in the sectors you have ruled out, reads
each remaining posting for visa language, and publishes a dashboard.

You never run anything. GitHub runs it and emails you what is new.

---

## Setting it up

You do not need to know how GitHub works. This is about fifteen minutes, once.

### 1. Make an account

Go to github.com and sign up. Free is fine.

### 2. Make a repository

Click the **+** at the top right, then **New repository**.

- Repository name: `job-radar`
- Set it to **Public**
- Do not tick "Add a README file"
- Click **Create repository**

> Public matters: GitHub only publishes web pages from public repositories on
> free accounts. Nothing personal goes in here, only public job listings. The
> one exception is `config/outreach_companies.txt`, described further down. If
> you would rather that list stayed private, just leave the file out.

### 3. Upload the files

On the empty repository page, click **uploading an existing file**.

Unzip `job-radar.zip` on your computer, open the folder, select everything
inside it, and drag it all onto the upload area. Make sure you drag the
*contents* of the folder, not the folder itself.

Scroll down, click **Commit changes**.

### 4. Turn on the daily run

Click the **Actions** tab. GitHub will ask whether to enable workflows.
Click **I understand my workflows, go ahead and enable them**.

### 5. Turn on the web page

Go to **Settings**, then **Pages** in the left sidebar.
Under Source, choose **GitHub Actions**. That is the only change.

### 6. Run it once by hand

Back to the **Actions** tab. Click **Job Radar** in the left sidebar, then the
**Run workflow** button on the right, then the green **Run workflow**.

The first run takes about ten minutes because it has to work out which system
each of the 270 employers uses to post jobs. Every run after that takes two or
three minutes.

When it finishes, your dashboard is at:

```
https://YOUR-USERNAME.github.io/job-radar/
```

Bookmark it. It refreshes itself every morning at 07:30 Copenhagen time.

### 7. Get the daily email

Every morning the run also opens a GitHub issue listing the new openings, and
GitHub emails it to you. To make sure it does, click the **Watch** button near
the top of the repository, choose **Custom**, and tick **Issues**.

If you would rather not get email, skip this and just check the dashboard.

---

## Making it wider

Two optional API keys widen the net considerably. Both are free and take about
two minutes each. Skip them if you want; everything works without them.

**Adzuna** covers general job boards in eight countries, which catches the
laboratory, field and analyst roles that never reach a specialist board.
Sign up at developer.adzuna.com, get an App ID and an App Key.

**USAJOBS** covers federal openings at NOAA, NIH, USGS and the Smithsonian.
Most federal roles need citizenship and the dashboard marks them blocked, but
a handful are open to non-citizens and those are worth seeing.
Sign up at developer.usajobs.gov.

To add them: **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Add them one at a time with these exact names:

| Name | Value |
|---|---|
| `ADZUNA_APP_ID` | your Adzuna app id |
| `ADZUNA_APP_KEY` | your Adzuna app key |
| `USAJOBS_KEY` | your USAJOBS key |
| `USAJOBS_EMAIL` | the email you registered with |

---

## Reading the dashboard

The coloured bar down the left of each row is the F-1 read:

| Colour | Meaning |
|---|---|
| green | the posting says it sponsors, or names OPT, CPT or F-1 |
| blue | H-1B cap exempt employer, no blocking language |
| grey | nothing said either way, which is most postings |
| brown | language that usually means no sponsorship |
| red | citizenship, clearance or ITAR required |
| dark | outside the US, so F-1 does not apply |

**Cap exempt** is the tag worth learning. Universities, their affiliated
nonprofits, and nonprofit research institutes are exempt from the H-1B lottery,
so they can file a petition any month of the year instead of competing for the
March cap. For someone graduating on an F-1 that is the single biggest
structural advantage in the US market, which is why those employers are scored
up and get their own filter.

None of this is a verified database. Treat green as reliable and everything
else as a starting point for the question you ask the recruiter.

The bar chart across the top counts new postings per day over the last month,
so you can see when hiring cycles open. Expect it to be quiet through August
and to climb through September and October as May 2027 graduate roles post.

**Mark applied** is stored in your browser only, so it lives on whichever
device you use. It is not shared and not committed.

---

## Tuning it

Everything is in `config/`. Edit the files on GitHub by clicking the file, then
the pencil icon, then **Commit changes**. The next run picks up the change.

**`organizations.yaml`** is the employer list. Add a line to watch a new
employer. You do not need to know which system they use:

```yaml
  - {name: Some Marine Startup, cat: marine, country: US}
```

Then run the workflow once with rediscovery, or just wait for Sunday, when it
re-probes everything automatically.

**`profile.yaml`** is you: the skills, techniques and field experience a
posting gets matched against. This is what produces the green overlap tags and
the "your niche" flag. Add anything you can honestly claim, remove anything you
would not want asked about in an interview. Do not put visa status or personal
details in it; the sponsorship logic does not read this file.

**`programs.yaml`** is the deadline calendar: post-bacs, fellowships and
early-career intakes, none of which appear on job boards. Every entry carries a
`status`:

- `eligible` — read off the programme's own page on the `checked` date,
  including its eligibility rules. Act on these.
- `unverified` — not yet checked. Every date and eligibility claim is a guess.
- `ineligible` — verified, and you cannot apply. Kept on purpose so the same
  dead end is not rediscovered in six months. Never surfaced as an action.

The first version of this file was written from general knowledge, and when the
entries were checked against their sources, four of the first seven were wrong
in ways that mattered, including the one ranked first, which requires US
citizenship. Hence the status field. Verify before trusting anything marked
unverified, and change its status when you do.

**The structural trap worth internalising.** You graduate May 2027, so summer
2027 is post-graduation, and most undergraduate summer research programmes
require enrolment through the start date. That rules out more of the American
programme landscape than the citizenship bar does. What works: post-bacs and
early-career programmes starting after graduation, programmes that accept
recent graduates, autumn recruiting for 2027 full-time starts, and non-US
options where an F-1 is irrelevant.

**`taxonomy.yaml`** decides what counts. Four tiers:

- `core` is the strongest signal and always qualifies a posting
- `domain` is subject matter and always qualifies a posting
- `role` is job shape, like "research assistant", and only qualifies when the
  employer is one of yours or the posting also mentions the subject. This is
  what stops every Data Analyst opening in the country from flooding in
- `supporting` only sharpens the ranking, never qualifies anything

`exclude` drops a posting outright on any hit. The seniority and machine
learning lists are checked against the title, the sector list against the whole
posting.

**`settings.yaml`** holds the knobs worth touching:

| Setting | Does what |
|---|---|
| `min_relevance` | how strong a match has to be. Lower widens, raise if noisy |
| `min_relevance_lowtrust` | the higher bar RSS boards must clear, since they send a title and a link and nothing else |
| `max_age_days` | anything the employer dated older than this is dropped |
| `stale_after_days` | past this a posting is shown but marked ageing |
| `drop_blocked` | removes roles needing citizenship, permanent residence or a clearance |

**Doctorate filtering.** Roles requiring a PhD are dropped. This is parsed rather
than phrase-matched: the doctorate mention is found, then the surrounding words
decide whether it is a bar. "Ph.D. in molecular biology is required" drops.
"MS or PhD" is kept, because a master's is an accepted alternative. "PhD
preferred" is kept, because preferred is not required. Postdoc and PhD-student
titles drop on the title alone. An earlier version used a fixed phrase list and
caught only about a third of real phrasings.

**On places.** `settings.yaml` has a `priority_locations` block for the west
coast, Copenhagen and India. Postings there get a scoring bonus and a badge, so
a good role in San Diego outranks an equally good one in Ohio. This only affects
ranking, never filtering, and there is a filter row for the three of them.

**On deadlines.** A closing date is only shown when the employer states one, in
the text or a structured field. Nothing is inferred from the posting date, so
"no deadline stated" means exactly that. Postings that say they review on a
rolling basis are labelled that way, since early beats on-time there. Anything
closing within a fortnight gets a red CLOSING tag and jumps the default sort.

**On dates.** Employer career pages publish a real publication date and those
are marked exact. Feeds publish one but re-date items when they re-syndicate,
so those show a tilde and are treated as roughly right. Some conservation
boards publish no date at all; those are kept, marked "no date published", and
never allowed to rank as fresh. Nothing is invented.

**`config/outreach_companies.txt`** is optional. Put one company name per line,
straight out of your outreach tracker, and any opening at those companies gets
an "already contacted" tag so you do not cold email somebody you are already in
a thread with.

---

## Running it on your own laptop instead

```bash
pip install -r requirements.txt
python run.py
open docs/index.html
```

Useful flags: `--rediscover` re-probes every career page, `--verbose` shows what
got dropped and why, `--digest` writes `digest.md`.

---

## How the registry checks itself

I built the 449 employer list from my own knowledge and could not verify it:
the environment I develop in cannot reach career pages, and I cannot
programmatically hit hundreds of board endpoints. So the verification is built
into the tool, which runs where the network is open.

Every run probes six applicant tracking systems per unresolved employer and
records what answered. Results land in `data/registry_health.json` and on the
dashboard under "employer registry coverage":

- **resolved** — a live public feed was found and read. Re-verified every 30
  days, because employers migrate between systems and a stale cache quietly
  stops returning postings without erroring.
- **not resolved, retrying** — missed this run. Retried next run. A single
  network blip no longer removes an employer, which was a real bug in the
  first version.
- **quarantined** — four separate runs found nothing. Either the employer uses
  a system with no public API, Workday being the common case, or the name in
  my registry does not match reality. These are the ones to prune or fix.

To act on it: open the quarantined list, delete the entries that are junk, and
for the ones you want to keep, find their real board URL and put the slug in
`hints`. Quarantined employers are retried every 90 days anyway, so a genuine
outage recovers on its own.

Expect the resolve rate to be well short of 100%. Large pharma, most
universities and many NGOs run Workday or a custom system with no public feed.
That is a real limit of this approach, not a bug.

## When something looks wrong

Open the **Actions** tab and click the most recent run to see the log. It lists
every source and how many postings it returned, then every reason postings were
dropped and how many. If a specialist board has changed its feed address it
logs a line and carries on rather than failing the run, so check there first
if a source you expected has gone quiet.

The employer discovery cache lives in `data/boards.json`. Any organization
showing `null` could not be resolved, usually because it uses Workday or a
custom system with no public feed. Those still need checking by hand.
