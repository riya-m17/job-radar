"""Two screens that run before anything reaches the dashboard.

SCREEN A: does this posting count undergraduate research?

Two postings can state the same nominal bar and mean opposite things, which is
what makes this worth parsing rather than eyeballing.

    Arc Institute: "2+ years of relevant experience (including independent lab
    work during your undergraduate studies)". The parenthesis is the whole
    posting. She qualifies.

    Freenome: "Bachelors with 1+ years of relevant industry experience or
    Masters". No carve-out, and a summer internship is not a year of industry.
    She does not qualify and no cover letter changes that.

Three buckets: qualifies, excluded, ambiguous. Excluded postings are not
deleted, they are demoted to a low-priority bucket, because a filter you cannot
see is a filter you cannot correct. The exact clause is quoted on the row.

SCREEN B: tier D duty density.

Requirements sections are written loosely and joined by "or", so they overstate
fit. "Extensive hands-on experience with cloning, PCR, qPCR, or plasmid
preparation" passes on PCR alone. The duties section is what the person does
all day, and that is the honest signal.

The worked example is Twist Bioscience, Research Associate Antibody
Engineering: it passes on requirements because of PCR, but seven of eight
duties were tier D. So tier D terms are counted in the duties section only, and
a high ratio marks a category mismatch however well the requirements read.

Both screens include false-friend handling, because a shared word is not a
shared skill and keyword matching produces exactly the overclaiming that gets
caught in an interview.
"""

from __future__ import annotations

import re

from .util import log, text_of

# ------------------------------------------------------------------ tier D
# Things she has not done at all. Regex so stems and variants both match.
TIER_D = {
    # NOTE ON THE REGEXES: leading \b only, never a trailing one. A trailing
    # \b after a stem can never match, because "flow cytometr" is followed by
    # "y", which is not a word boundary. That bug silently hid two of the
    # eleven tier D categories.
    "wet-lab cloning": r"\b(molecular cloning|restriction (?:cloning|digest)"
                       r"|gibson assembl|golden gate|subclon|colony pick"
                       r"|bacterial transformation|plasmid construction)",
    "NGS library prep": r"\b(librar\w*\s+(?:prep|construct)"
                        r"|prepar\w*\s+\w*\s?librar|adapter ligation"
                        r"|index\w*\s+pcr|ngs librar)",
    "target capture": r"\b(target(?:ed)? capture|hybrid\w+ capture"
                      r"|exome capture|bait design|probe panel)",
    "microtomy/FFPE": r"\b(microtom|cryosection|ffpe|paraffin|tissue section"
                      r"|embedding block|sectioning)",
    "flow cytometry": r"\b(flow cytometr|facs|fluorescence[- ]activated cell sort"
                      r"|cell sorting|cytometer)",
    "phage/yeast display": r"\b(phage display|yeast display|biopanning"
                           r"|display librar|panning round)",
    "ELISA": r"\b(elisa|enzyme[- ]linked immunosorbent)",
    "SPR/BLI": r"\b(surface plasmon resonance|spr\b|biolayer interferometr"
               r"|bli\b|octet|biacore|binding kinetic)",
    "iPSC/neural culture": r"\b(ipsc|induced pluripotent|organoid"
                           r"|neural (?:stem )?cell|neuron differentiation"
                           r"|stem cell culture)",
    "protein purification": r"\b(protein purification|affinity chromatograph"
                            r"|immunoprecipitat|his[- ]tag purif"
                            r"|size exclusion chromatograph|fplc)",
    "CRISPR screens": r"\b(crispr screen|pooled screen|guide rna librar"
                      r"|knockout screen|sgrna librar)",
}


# A shared word is not a shared skill. Each entry is (trap, hers, note).
FALSE_FRIENDS = [
    (r"\bphage display\b", r"\bphage genome analysis\b",
     "phage display is wet-lab selection; hers is computational phage genomics"),
    (r"\bspatial (?:multi-?omics|transcriptomics) platform\b",
     r"\bspatial transcript mapping\b",
     "platform development is not the same as running RNAscope mapping"),
    (r"\blibrary prep(?:aration)?\b", r"\banaly[sz]ing sequencing librar",
     "analysing libraries is not preparing them"),
    (r"\b(?:molecular |restriction )?cloning\b", r"\bbenchling\b",
     "Benchling construct design is not bench cloning"),
]

# --------------------------------------------------------------- sections
DUTY_HEADS = re.compile(
    r"(what you.{0,20}(?:do|ll be doing)|responsibilities|duties|role overview"
    r"|day[- ]to[- ]day|in this role|key activities|essential functions"
    r"|the opportunity|about the role|position summary)", re.I)
REQ_HEADS = re.compile(
    r"(requirements|qualifications|what you.{0,20}(?:bring|have|need)"
    r"|about you|who you are|skills and experience|minimum qualifications"
    r"|preferred qualifications|we.{0,10}re looking for|basic qualifications)", re.I)


def split_sections(text: str) -> tuple[str, str]:
    """Return (duties, requirements). Falls back to the whole text."""
    if not text:
        return "", ""
    marks = []
    for m in DUTY_HEADS.finditer(text):
        marks.append((m.start(), "duty"))
    for m in REQ_HEADS.finditer(text):
        marks.append((m.start(), "req"))
    if not marks:
        return text, text
    marks.sort()
    duties, reqs = [], []
    for i, (pos, kind) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        (duties if kind == "duty" else reqs).append(text[pos:end])
    return (" ".join(duties) or text), (" ".join(reqs) or text)


# ============================================================== SCREEN A
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:to|-|–|or more)?\s*\d{0,2}\s*year", re.I)

# Language that explicitly counts academic or undergraduate work.
CARVE_OUT = re.compile(
    r"(includ\w*\s+(?:independent\s+)?(?:lab|laboratory|research)\s+work\s+"
    r"during\s+(?:your\s+)?undergraduate"
    r"|including\s+(?:undergraduate|academic|university|college|research)"
    r"|(?:undergraduate|academic|research|university|coursework|thesis)\s+"
    r"(?:lab\s+)?experience\s+(?:counts|qualifies|is\s+(?:accepted|considered))"
    r"|academic\s+or\s+industry|industry\s+or\s+academic"
    r"|research\s+or\s+industry|industry\s+or\s+research"
    r"|equivalent\s+(?:academic|research|practical|combination)"
    r"|or\s+equivalent\s+experience"
    r"|internship\w*\s+(?:count|qualif|includ)"
    r"|including\s+time\s+as\s+a\s+student)", re.I)

# Language that specifically demands industry or professional time.
INDUSTRY_ONLY = re.compile(
    r"((?:\d{1,2}\s*\+?\s*years?[^.;]{0,40})?(?:industry|professional|commercial"
    r"|post[- ]graduate|post[- ]college|full[- ]time work)\s+experience"
    r"|experience\s+in\s+(?:a\s+)?(?:biotech|pharma|industry|commercial)\s+setting"
    r"|working\s+in\s+industry)", re.I)

DEGREE_ONLY = re.compile(
    r"(master'?s?\s+(?:degree\s+)?(?:required|is required|or)"
    r"|requires?\s+a\s+master'?s"
    r"|m\.?s\.?\s+required"
    r"|bachelors?\s+with\s+\d\s*\+?\s*years?\s+of\s+relevant\s+industry)", re.I)


def _quote(text: str, match: re.Match, width: int = 120) -> str:
    start = max(0, match.start() - 40)
    end = min(len(text), match.end() + width)
    return " ".join(text[start:end].split())


def screen_experience(job: dict) -> dict:
    """Screen A. Does this posting count her undergraduate research?"""
    text = text_of(job, "description", 12000)
    if not text:
        return {"exp_screen": "ambiguous",
                "exp_reason": "no posting text to read",
                "exp_quote": ""}

    _, reqs = split_sections(text)
    scope = reqs or text

    # A posting saying it wants no experience is the opposite of a bar, and
    # without this the friendliest postings get flagged as ambiguous.
    no_exp = re.search(
        r"(no (?:prior |previous )?(?:industry |professional |work )?"
        r"experience (?:is )?(?:required|necessary|needed)"
        r"|entry[- ]level position|new grad(?:uate)?s? (?:welcome|encouraged)"
        r"|0\s*[-\u2013]\s*\d\s*years)", scope, re.I)
    if no_exp:
        return {"exp_screen": "qualifies",
                "exp_reason": "states no experience minimum",
                "exp_quote": _quote(scope, no_exp)}

    carve = CARVE_OUT.search(scope)
    years = _YEARS.search(scope)
    industry = INDUSTRY_ONLY.search(scope)
    degree = DEGREE_ONLY.search(scope)

    # An explicit carve-out settles it, whatever the number of years.
    if carve:
        return {"exp_screen": "qualifies",
                "exp_reason": "counts academic or undergraduate experience",
                "exp_quote": _quote(scope, carve)}

    # A degree bar above bachelor's with no equivalence clause.
    if degree:
        return {"exp_screen": "excluded",
                "exp_reason": "asks for a master's with no equivalent-experience clause",
                "exp_quote": _quote(scope, degree)}

    # Industry or professional time demanded, no carve-out found.
    if industry:
        n = int(years.group(1)) if years else 0
        if n >= 1:
            return {"exp_screen": "excluded",
                    "exp_reason": f"wants {n}+ years of industry experience, no academic carve-out",
                    "exp_quote": _quote(scope, industry)}
        return {"exp_screen": "ambiguous",
                "exp_reason": "mentions industry experience without a stated number",
                "exp_quote": _quote(scope, industry)}

    if years:
        n = int(years.group(1))
        if n == 0:
            return {"exp_screen": "qualifies", "exp_reason": "no experience minimum",
                    "exp_quote": _quote(scope, years)}
        return {"exp_screen": "ambiguous",
                "exp_reason": f"asks for {n}+ years but does not say whether academic work counts",
                "exp_quote": _quote(scope, years)}

    return {"exp_screen": "qualifies", "exp_reason": "no experience requirement stated",
            "exp_quote": ""}


# ============================================================== SCREEN B
def screen_duties(job: dict) -> dict:
    """Screen B. What fraction of the daily work is tier D?"""
    text = text_of(job, "description", 12000)
    if not text:
        return {"tier_d_terms": [], "tier_d_count": 0, "duty_bullets": 0,
                "tier_d_density": 0.0, "category_mismatch": False,
                "false_friends": []}

    duties, _ = split_sections(text)
    low = duties.lower()

    hits = [name for name, pattern in TIER_D.items() if re.search(pattern, low)]

    # Count bullets to get a denominator. Falls back to sentences.
    bullets = len(re.findall(r"(?:^|\n)\s*[-•*\u2022]\s*\S", duties))
    if bullets < 2:
        bullets = max(1, len([s for s in re.split(r"[.;]\s", duties) if len(s) > 25]))

    density = len(hits) / bullets if bullets else 0.0

    friends = []
    whole = text.lower()
    for trap, hers, note in FALSE_FRIENDS:
        if re.search(trap, whole) and not re.search(hers, whole):
            friends.append(note)

    # Most of the day is work she has never done.
    mismatch = len(hits) >= 3 and density >= 0.4

    return {"tier_d_terms": sorted(hits),
            "tier_d_count": len(hits),
            "duty_bullets": bullets,
            "tier_d_density": round(density, 2),
            "category_mismatch": mismatch,
            "false_friends": friends}


def apply(job: dict) -> dict:
    """Run both screens and set a single priority bucket."""
    out = {}
    out.update(screen_experience(job))
    out.update(screen_duties(job))

    if out["exp_screen"] == "excluded" or out["category_mismatch"]:
        out["bucket"] = "low"
    elif out["exp_screen"] == "ambiguous" or out["tier_d_count"] >= 2:
        out["bucket"] = "review"
    else:
        out["bucket"] = "primary"
    return out


def summarise(jobs: list[dict]) -> None:
    counts: dict[str, int] = {}
    for j in jobs:
        counts[j.get("bucket", "primary")] = counts.get(j.get("bucket", "primary"), 0) + 1
    log.info("screens: %d primary, %d needs review, %d low priority",
             counts.get("primary", 0), counts.get("review", 0), counts.get("low", 0))
