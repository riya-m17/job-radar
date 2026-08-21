#!/usr/bin/env python3
"""Regression suite. Run before shipping any change: python selftest.py

Written after a session in which several filters looked correct and were not.
Each block asserts both directions: that the thing meant to be dropped drops,
and that the thing meant to survive survives. The second half matters more,
since an over-aggressive filter empties the dashboard silently.
"""

from __future__ import annotations

import datetime as dt
import sys

sys.path.insert(0, ".")

from radar import (classify, deadlines, freshness, profile_match, programs,
                   render, requirements, store, visa)

PASS, FAIL = [], []


def check(name: str, got, want) -> None:
    (PASS if got == want else FAIL).append((name, got, want))


def job(**kw) -> dict:
    base = dict(title="", description="", company="Acme Bio", location="Boston, MA",
                department="", source="greenhouse", url="https://x.com/jobs/1",
                org_cat="genomics", country_hint="US",
                posted=dt.date.today().isoformat(),
                first_seen=dt.date.today().isoformat())
    base.update(kw)
    return base


def survives(**kw) -> bool:
    """Run a posting through the whole gauntlet the way run.py does."""
    j = job(**kw)
    r = classify.classify(j)
    if r is None:
        return False
    r.update(visa.assess(r))
    if r["visa_status"] == "blocked":
        return False
    r.update(freshness.assess(r))
    if freshness.too_old(r):
        return False
    r.update(requirements.assess(r))
    if requirements.rejected(r):
        return False
    if r["role_type"] in ("internship", "seasonal"):
        return False
    return True


# --------------------------------------------------------------- robustness
JUNK = {k: None for k in ("title", "description", "company", "location",
                          "department", "source", "url", "region", "org_cat",
                          "sponsorship_declared", "country_hint")}
WEIRD = dict(title=123, description=["a"], company={"x": 1}, location=3.14,
             department=None, source="greenhouse", url="https://x",
             region="US", org_cat="genomics", posted=9999999999999,
             first_seen=None)
HUGE = job(title="Scientist " * 300, description="genomics " * 15000)

for label, payload in [("null", JUNK), ("empty", {}), ("weird", WEIRD), ("huge", HUGE)]:
    for fname, fn in [("classify", classify.classify), ("visa", visa.assess),
                      ("freshness", freshness.assess),
                      ("requirements", requirements.assess),
                      ("deadlines", deadlines.assess),
                      ("profile", profile_match.assess)]:
        try:
            fn(dict(payload))
            check(f"robust {fname}/{label}", True, True)
        except Exception as exc:
            check(f"robust {fname}/{label}", f"{type(exc).__name__}: {exc}", True)

# ------------------------------------------------------------------- drops
DROP = [
    ("PhD required", dict(title="Scientist", description="PhD required in genomics")),
    ("PhD, alt phrasing", dict(title="Scientist", description="Ph.D. in biology is required")),
    ("doctorate essential", dict(title="Scientist", description="A doctorate is essential")),
    ("postdoc title", dict(title="Postdoctoral Fellow", description="genomics")),
    ("phd student title", dict(title="PhD Student Position", description="genomics")),
    ("PhD intent required", dict(title="Research Associate",
     description="genomics. You must explicitly wish to use this experience to gain entry into a PhD program")),
    ("5 years", dict(title="Scientist", description="genomics, 5+ years of industry experience")),
    ("three years spelled", dict(title="Analyst",
     description="genomics, at least three years experience in programme delivery")),
    ("uni bench role", dict(title="Research Technician", company="Harvard University",
     description="genomics bench work in the laboratory of Dr Smith")),
    ("citizenship", dict(title="Biologist", description="wildlife biology. U.S. citizenship is required")),
    ("permanent resident", dict(title="Analyst", description="genomics. Must be a citizen or permanent resident")),
    ("clearance", dict(title="Analyst", description="genomics. Requires a security clearance")),
    ("software engineer", dict(title="Software Engineer", description="Build APIs")),
    ("full stack", dict(title="Full Stack Engineer", description="React and Node")),
    ("platform eng", dict(title="Platform Engineer", description="Kubernetes")),
    ("ML engineer", dict(title="Machine Learning Engineer", description="genomics models")),
    ("senior", dict(title="Senior Scientist", description="genomics")),
    ("alt protein", dict(title="Scientist", description="cultivated meat and genomics")),
    ("too old", dict(title="Genomics Analyst", description="genomics",
     posted=(dt.date.today() - dt.timedelta(days=200)).isoformat())),
    ("internship", dict(title="Summer Intern", description="genomics internship")),
]
for name, kw in DROP:
    check("drop: " + name, survives(**kw), False)

# ------------------------------------------------------------------- keeps
KEEP = [
    ("bioinformatics analyst", dict(title="Bioinformatics Analyst I",
     description="Analyse genomics data in Python and R. BS required, 0-2 years")),
    ("MS or PhD", dict(title="Research Associate",
     description="genomics. MS or PhD with relevant experience")),
    ("PhD preferred", dict(title="Research Associate",
     description="genomics. PhD preferred but not required")),
    ("stepping stone", dict(title="Research Associate",
     description="genomics. A great stepping stone to graduate school")),
    ("two year post-bac", dict(title="Research Associate",
     description="genomics. Two year post-baccalaureate appointment")),
    ("2 years ok", dict(title="Analyst", description="genomics, 2 years of relevant experience")),
    ("bioinformatics engineer", dict(title="Bioinformatics Engineer",
     description="Build genomics pipelines in Python")),
    ("field app scientist", dict(title="Field Application Scientist", org_cat="genomics",
     description="Support customers running sequencing instruments, troubleshoot assays")),
    ("technical sales", dict(title="Technical Sales Specialist", org_cat="genomics",
     description="Sell genomics instruments to research labs")),
    ("illustrator", dict(title="Science Illustrator", org_cat="museum",
     description="Scientific illustration and exhibit design for public audiences")),
    ("editorial", dict(title="Editorial Assistant", org_cat="media",
     description="Editorial support on manuscripts and science writing")),
    ("museum educator", dict(title="Museum Educator", org_cat="museum",
     description="Public engagement and interpretive marine biology programmes")),
    ("institute RA", dict(title="Research Technician", company="Broad Institute",
     org_cat="institute", description="Sequencing operations and genomics support")),
    ("marine acoustics", dict(title="Marine Data Analyst", org_cat="marine",
     description="Passive acoustic monitoring of marine mammals, hydrophone data, Python")),
]
for name, kw in KEEP:
    check("keep: " + name, survives(**kw), True)

# ------------------------------------------------------------ region + place
for loc, want in [("New York, New York", "US"), ("San Diego, CA", "US"),
                  ("Copenhagen, Denmark", "Denmark"), ("Bengaluru, India", "India"),
                  ("London, United Kingdom", "UK")]:
    r = classify.classify(job(title="Bioinformatics Analyst",
                              description="genomics", location=loc))
    check(f"region {loc or 'empty'}", r["region"] if r else None, want)

# An empty location on a US employer is correctly labelled US, because the
# registry knows where the employer is. Only a posting with no location AND no
# known employer country is genuinely unplaceable.
r = classify.classify(job(title="Bioinformatics Analyst", description="genomics",
                          location="", country_hint=""))
check("region truly unknown", r["region"] if r else None, "Not stated")
r = classify.classify(job(title="Bioinformatics Analyst", description="genomics",
                          location="", country_hint="US"))
check("region empty but US employer", r["region"] if r else None, "US")

for loc, want in [("San Diego, CA", "west_coast"), ("Seattle, WA", "west_coast"),
                  ("Copenhagen, Denmark", "copenhagen"), ("Mumbai, India", "india"),
                  ("Columbus, OH", "")]:
    r = classify.classify(job(title="Bioinformatics Analyst",
                              description="genomics", location=loc))
    check(f"place {loc}", r["priority_place"] if r else None, want)

# ----------------------------------------------------------------- flavours
for title, desc, want in [
        ("Field Application Scientist", "support customers", "commercial"),
        ("Marine Data Analyst", "acoustic data in Python", "computational"),
        ("Science Illustrator", "visual illustration", "creative"),
        ("Research Technician", "cell culture and PCR bench work", "bench"),
        ("Museum Educator", "public engagement programmes", "comms")]:
    r = classify.classify(job(title=title, description=desc + " genomics",
                              org_cat="museum"))
    check(f"flavour {title}", want in (r["flavours"] if r else []), True)

# ------------------------------------------------------------------- visa
for region, desc, want in [
        ("US", "We sponsor H-1B visas", "explicit"),
        ("US", "no sponsorship available", "unlikely"),
        ("US", "great benefits", "unknown"),
        ("UK", "must have the right to work in the UK", "unlikely"),
        ("Denmark", "join our Copenhagen team", "permit"),
        ("Denmark", "we support work permits and relocation", "explicit"),
        ("Not stated", "great role", "unknown")]:
    check(f"visa {region}/{desc[:18]}",
          visa.assess({"title": "x", "description": desc, "region": region})["visa_status"],
          want)

# --------------------------------------------------------------- deadlines
for desc, want in [("Applications close on 15 January 2027.", "stated"),
                   ("Deadline: 2026-09-30", "stated"),
                   ("Apply by October 3, 2026", "stated"),
                   ("Reviewed on a rolling basis until filled", "rolling"),
                   ("Join our team in San Diego", "none"),
                   ("This is a 2 year programme starting September 2026", "none"),
                   ("Applications closed on 1 March 2020", "none")]:
    check(f"deadline {desc[:26]}",
          deadlines.assess({"description": desc, "title": ""})["closes_kind"], want)

# ---------------------------------------------------------------- calendar
cal = programs.load()
check("calendar loads", len(cal) > 0, True)
check("no ineligible in act panel",
      all(p.get("status") != "ineligible" for p in programs.act_now(cal)), True)
check("no internships in act panel",
      all(p.get("type") not in ("internship", "seasonal") for p in programs.act_now(cal)), True)

# ------------------------------------------------------------------- dedup
from radar import dedup, screens

def _dj(**k):
    return dict({"title": "", "company": "", "location": "Boston, MA",
                 "url": "", "source": "greenhouse", "description": "x"}, **k)

for name, a, b, should_merge in [
    ("greenhouse two hosts",
     _dj(company="Illumina", title="Analyst I", url="https://boards.greenhouse.io/illumina/jobs/1"),
     _dj(company="Illumina", title="Analyst I", url="https://job-boards.greenhouse.io/illumina/jobs/1"), True),
    ("tracking parameter",
     _dj(company="Arc", title="RA II", url="https://boards.greenhouse.io/arc/jobs/9"),
     _dj(company="Arc", title="RA II", url="https://boards.greenhouse.io/arc/jobs/9?gh_src=x"), True),
    ("level variants",
     _dj(company="Broad", title="Research Associate I/II", url="https://a/1", source="climatebase"),
     _dj(company="Broad", title="Research Associate II", url="https://b/2", source="remotive"), True),
    ("roman vs digit",
     _dj(company="Broad", title="Scientist 2", url="https://a/1", source="climatebase"),
     _dj(company="Broad", title="Scientist II", url="https://b/2", source="remotive"), True),
    ("different cities stay split",
     _dj(company="Illumina", title="FAS", location="San Diego, CA", url="https://boards.greenhouse.io/i/jobs/1"),
     _dj(company="Illumina", title="FAS", location="Boston, MA", url="https://boards.greenhouse.io/i/jobs/2"), False),
    ("different roles stay split",
     _dj(company="Illumina", title="Analyst", url="https://boards.greenhouse.io/i/jobs/1"),
     _dj(company="Illumina", title="FAS", url="https://boards.greenhouse.io/i/jobs/2"), False),
]:
    out, _ = dedup.deduplicate([dict(a), dict(b)])
    check("dedup: " + name, len(out) == 1, should_merge)

check("dedup is idempotent",
      len(dedup.deduplicate([_dj(company="X", title="Y",
                                 url="https://boards.greenhouse.io/x/jobs/1")] * 5)[0]), 1)

# ----------------------------------------------------------------- screens
ARC = ("Requirements: 2+ years of relevant experience (including independent "
       "lab work during your undergraduate studies).")
FREENOME = ("Qualifications: Bachelors with 1+ years of relevant industry "
            "experience or Masters.")
NOEXP = "Requirements: BS in biology. No prior industry experience required."
VAGUE = "Requirements: 3+ years of relevant experience. BS required."
TWIST = ("What you will do:\n- Perform phage display selections\n"
         "- Execute yeast display library sorting\n- Run flow cytometry\n"
         "- Perform protein purification and immunoprecipitation\n"
         "- Conduct ELISA and SPR assays\n- Prepare NGS libraries\n"
         "- Perform molecular cloning and Gibson assembly\n"
         "- Analyse data in Python\n"
         "Requirements: hands-on experience with cloning, PCR, qPCR, or plasmid preparation.")

check("screenA arc counts undergrad",
      screens.screen_experience({"description": ARC})["exp_screen"], "qualifies")
check("screenA freenome excluded",
      screens.screen_experience({"description": FREENOME})["exp_screen"], "excluded")
check("screenA no-experience is not a bar",
      screens.screen_experience({"description": NOEXP})["exp_screen"], "qualifies")
check("screenA vague is ambiguous",
      screens.screen_experience({"description": VAGUE})["exp_screen"], "ambiguous")
check("screenA quotes the clause",
      len(screens.screen_experience({"description": ARC})["exp_quote"]) > 20, True)

tw = screens.screen_duties({"description": TWIST})
check("screenB counts tier D duties", tw["tier_d_count"] >= 7, True)
check("screenB flags category mismatch", tw["category_mismatch"], True)
check("screenB catches false friends", len(tw["false_friends"]) >= 1, True)
check("screenB clean role not flagged",
      screens.screen_duties({"description":
          "What you will do:\n- Analyse genomics data in Python\n"
          "- Build pipelines\n- Present findings"})["category_mismatch"], False)
check("twist lands in low bucket", screens.apply({"description": TWIST})["bucket"], "low")
check("arc lands in primary bucket", screens.apply({"description": ARC})["bucket"], "primary")

# ------------------------------------------------------------------ config
check("stale threshold from config", store._stale_threshold(), 2)

# ------------------------------------------------------------------ render
html = render.build([], {}, cal)
check("html renders empty", "<html" in html and "</html>" in html, True)
check("html braces balanced", html.count("{") == html.count("}"), True)

# ------------------------------------------------------------------ report
print(f"\n{len(PASS)} passed, {len(FAIL)} failed\n")
if FAIL:
    print("FAILURES")
    for name, got, want in FAIL:
        print(f"  {name}\n     got  {got!r}\n     want {want!r}")
    sys.exit(1)
print("all clear")
