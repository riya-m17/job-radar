"""Build the dashboard.

The page is styled as a field survey ledger rather than a job board: dense
rows, a monospace data column, and a detection histogram across the header
showing how many new postings landed each day for the last month. The colour
down the left edge of every row is the F-1 verdict, so the page can be
triaged without reading a word.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from .util import ROOT, load_config, log, settings

CATEGORIES = load_config("taxonomy")["categories"]

CSS = """
:root{
  --ink:#0A1418; --shelf:#101F26; --raise:#16303A; --rule:#1E333D;
  --ice:#DCE8ED; --fog:#7C949F; --dim:#4E6874;
  --kelp:#5FA37E; --glacier:#6FA8C7; --amber:#D9A441; --rust:#C4614F;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  background:var(--ink); color:var(--ice);
  font-family:'IBM Plex Sans',system-ui,sans-serif;
  font-size:15px; line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace}
.wrap{max-width:1180px;margin:0 auto;padding:0 22px}

/* ---------------------------------------------------------- masthead */
header{border-bottom:1px solid var(--rule);padding:34px 0 0}
.title{
  font-family:'Fraunces',Georgia,serif; font-weight:600;
  font-size:clamp(30px,5vw,46px); letter-spacing:-.02em; line-height:1.05;
  font-variation-settings:'SOFT' 40,'WONK' 1;
}
.sub{color:var(--fog);font-size:13.5px;margin-top:8px;max-width:62ch}
.stamp{
  font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--dim);margin-bottom:12px;
}
.stamp b{color:var(--glacier);font-weight:500}

/* --------------------------------------------- detection histogram */
.detect{margin:26px 0 0;padding-bottom:22px}
.detect-label{
  font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);display:flex;
  justify-content:space-between;align-items:baseline;margin-bottom:9px;
}
.bars{display:flex;align-items:flex-end;gap:3px;height:52px}
.bar{
  flex:1;min-width:3px;background:var(--raise);border-radius:1px 1px 0 0;
  position:relative;transition:background .15s;
}
.bar:hover{background:var(--glacier)}
.bar.today{background:var(--amber)}
.bar span{
  position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);
  background:var(--shelf);border:1px solid var(--rule);color:var(--ice);
  font-family:'IBM Plex Mono',monospace;font-size:10.5px;padding:3px 7px;
  white-space:nowrap;opacity:0;pointer-events:none;transition:opacity .12s;
  border-radius:2px;z-index:5;
}
.bar:hover span{opacity:1}

/* ------------------------------------------------------------ counts */
.counts{display:flex;flex-wrap:wrap;gap:0;border-top:1px solid var(--rule)}
.count{padding:16px 26px 16px 0;margin-right:26px;border-right:1px solid var(--rule)}
.count:last-child{border-right:0}
.count .n{font-family:'IBM Plex Mono',monospace;font-size:26px;line-height:1;letter-spacing:-.02em}
.count .k{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-top:6px}
.count.new .n{color:var(--amber)}
.count.exempt .n{color:var(--kelp)}

/* ----------------------------------------------------------- controls */
.controls{position:sticky;top:0;background:var(--ink);z-index:20;
  border-bottom:1px solid var(--rule);padding:14px 0 12px}
.search{
  width:100%;background:var(--shelf);border:1px solid var(--rule);color:var(--ice);
  font-family:'IBM Plex Mono',monospace;font-size:13px;padding:10px 13px;border-radius:3px;
}
.search:focus{outline:2px solid var(--glacier);outline-offset:1px;border-color:transparent}
.search::placeholder{color:var(--dim)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px}
.chip{
  font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.04em;
  background:transparent;border:1px solid var(--rule);color:var(--fog);
  padding:5px 10px;border-radius:2px;cursor:pointer;transition:all .12s;
}
.chip:hover{border-color:var(--dim);color:var(--ice)}
.chip[aria-pressed="true"]{background:var(--glacier);border-color:var(--glacier);color:var(--ink);font-weight:500}
.chip:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
.grouplabel{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);align-self:center;margin-right:2px}
details.drawer{margin-top:10px}
details.drawer>summary{
  font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.06em;
  color:var(--fog);cursor:pointer;list-style:none;display:inline-flex;gap:7px;
  align-items:center;border:1px solid var(--rule);padding:5px 10px;border-radius:2px;
}
details.drawer>summary::-webkit-details-marker{display:none}
details.drawer>summary:hover{color:var(--ice);border-color:var(--dim)}
details.drawer>summary:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
details.drawer>summary::after{content:'open';color:var(--dim);font-size:10px}
details.drawer[open]>summary::after{content:'close'}
.drawerbody{max-height:38vh;overflow-y:auto;padding:10px 0 2px;
  border-top:1px solid var(--rule);margin-top:10px}

/* --------------------------------------------------------------- rows */
.tally{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--dim);
  padding:16px 0 8px;letter-spacing:.05em}
.row{display:grid;grid-template-columns:4px 1fr auto;gap:0 16px;
  border-bottom:1px solid var(--rule);align-items:start}
.strip{align-self:stretch;background:var(--dim)}
.strip.explicit{background:var(--kelp)}
.strip.likely{background:var(--glacier)}
.strip.unknown{background:var(--dim)}
.strip.na{background:var(--raise)}
.strip.unlikely{background:#7A5B3A}
.strip.blocked{background:var(--rust)}
.body{padding:15px 0}
.rowtop{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.jtitle{font-size:15.5px;font-weight:500;letter-spacing:-.005em}
.jtitle a{color:var(--ice);text-decoration:none;border-bottom:1px solid transparent}
.jtitle a:hover{border-bottom-color:var(--glacier)}
.jtitle a:focus-visible{outline:2px solid var(--amber);outline-offset:3px}
.newtag{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.12em;
  background:var(--amber);color:var(--ink);padding:2px 6px;border-radius:2px;font-weight:600}
.meta{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--fog);
  margin-top:5px;display:flex;flex-wrap:wrap;gap:4px 12px}
.meta .co{color:var(--ice)}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}
.tag{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.05em;
  border:1px solid var(--rule);color:var(--fog);padding:2px 7px;border-radius:2px}
.tag.visa-explicit{color:var(--kelp);border-color:#2C5442}
.tag.visa-likely{color:var(--glacier);border-color:#2A4E60}
.tag.visa-blocked{color:var(--rust);border-color:#5A3029}
.tag.visa-unlikely{color:#C79A5E;border-color:#5A452C}
.tag.contact{color:var(--amber);border-color:#5A4720}
.side{padding:15px 0;text-align:right;display:flex;flex-direction:column;
  align-items:flex-end;gap:7px;min-width:96px}
.score{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--dim)}
.mark{font-family:'IBM Plex Mono',monospace;font-size:10.5px;background:transparent;
  border:1px solid var(--rule);color:var(--fog);padding:4px 9px;border-radius:2px;cursor:pointer}
.mark[aria-pressed="true"]{background:var(--kelp);border-color:var(--kelp);color:var(--ink)}
.mark:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
.row.done .body,.row.done .side{opacity:.42}
details.more{margin-top:10px}
details.more summary{font-family:'IBM Plex Mono',monospace;font-size:10.5px;
  color:var(--dim);cursor:pointer;letter-spacing:.06em;list-style:none}
details.more summary::-webkit-details-marker{display:none}
details.more summary:hover{color:var(--glacier)}
.detail{margin-top:9px;padding:12px 14px;background:var(--shelf);
  border-left:2px solid var(--rule);border-radius:0 2px 2px 0}
.detail p{font-size:13px;color:var(--fog);margin-bottom:8px}
.detail .why{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--glacier)}
.empty{padding:64px 0;text-align:center;color:var(--fog)}
.empty b{display:block;font-family:'Fraunces',serif;font-size:21px;color:var(--ice);margin-bottom:8px}
footer{border-top:1px solid var(--rule);margin-top:44px;padding:22px 0 60px;
  font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--dim);line-height:1.8}
@media (max-width:640px){
  .row{grid-template-columns:4px 1fr}
  .side{grid-column:2;text-align:left;align-items:flex-start;padding-top:0;padding-bottom:14px}
  .count{padding-right:18px;margin-right:18px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto}}
"""

JS = """
const DATA = __DATA__;
const state = {q:'', type:new Set(), cat:new Set(), visa:new Set(), region:new Set(),
               newOnly:false, exemptOnly:false, hideApplied:false, sort:'relevance'};
let applied = {};
try{ applied = JSON.parse(localStorage.getItem('radar-applied')||'{}'); }catch(e){}

const esc = s => (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const TYPE_LABEL = {full_time:'full time', new_grad:'new grad', internship:'internship',
                    fellowship:'fellowship', seasonal:'seasonal'};

function matches(j){
  if(state.newOnly && !j.is_new) return false;
  if(state.exemptOnly && !j.cap_exempt) return false;
  if(state.hideApplied && applied[j.key]) return false;
  if(state.type.size && !state.type.has(j.role_type)) return false;
  if(state.cat.size && !state.cat.has(j.org_cat)) return false;
  if(state.visa.size && !state.visa.has(j.visa_status)) return false;
  if(state.region.size && !state.region.has(j.region)) return false;
  if(state.q){
    const hay = (j.title+' '+j.company+' '+j.location+' '+(j.match_terms||[]).join(' ')).toLowerCase();
    if(!state.q.split(/\\s+/).every(t => hay.includes(t))) return false;
  }
  return true;
}

function render(){
  const rows = DATA.filter(matches).sort((a,b)=>
    state.sort==='date' ? (b.first_seen||'').localeCompare(a.first_seen||'') || b.relevance-a.relevance
                        : b.relevance-a.relevance || (b.first_seen||'').localeCompare(a.first_seen||''));
  document.getElementById('tally').textContent =
    rows.length + ' of ' + DATA.length + ' openings shown';
  const list = document.getElementById('list');
  if(!rows.length){
    list.innerHTML = '<div class="empty"><b>Nothing matches those filters.</b>'+
      'Clear a chip or widen the search to bring rows back.</div>';
    return;
  }
  list.innerHTML = rows.map(j => {
    const done = applied[j.key] ? ' done' : '';
    const terms = (j.match_terms||[]).slice(0,3).map(t=>'<span class="tag">'+esc(t)+'</span>').join('');
    return `<article class="row${done}" data-k="${j.key}">
      <div class="strip ${j.visa_status.replace('/','')}"></div>
      <div class="body">
        <div class="rowtop">
          <h2 class="jtitle"><a href="${esc(j.url)}" target="_blank" rel="noopener">${esc(j.title)}</a></h2>
          ${j.is_new?'<span class="newtag">NEW</span>':''}
        </div>
        <div class="meta">
          <span class="co">${esc(j.company)}</span>
          <span>${esc(j.location||j.region||'location not stated')}</span>
          <span>${esc(j.first_seen)}</span>
        </div>
        <div class="tags">
          <span class="tag visa-${j.visa_status.replace('/','')}">F-1 ${esc(j.visa_status)}</span>
          <span class="tag">${esc(TYPE_LABEL[j.role_type]||j.role_type)}</span>
          <span class="tag">${esc(j.cat_label)}</span>
          ${j.cap_exempt?'<span class="tag visa-likely">cap exempt</span>':''}
          ${j.already_contacted?'<span class="tag contact">already contacted</span>':''}
          ${terms}
        </div>
        <details class="more"><summary>why this surfaced</summary>
          <div class="detail">
            <div class="why">F-1 read: ${esc(j.visa_reason)}</div>
            ${j.snippet?'<p style="margin-top:8px">'+esc(j.snippet)+'</p>':''}
            <div class="why">source: ${esc(j.source)}</div>
          </div>
        </details>
      </div>
      <div class="side">
        <span class="score">score ${j.relevance}</span>
        <button class="mark" aria-pressed="${applied[j.key]?'true':'false'}">${applied[j.key]?'applied':'mark applied'}</button>
      </div>
    </article>`;
  }).join('');
}

document.addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if(chip){
    const {group, value} = chip.dataset;
    if(group==='flag'){ state[value] = !state[value]; chip.setAttribute('aria-pressed', state[value]); }
    else if(group==='sort'){
      state.sort = value;
      document.querySelectorAll('[data-group="sort"]').forEach(c =>
        c.setAttribute('aria-pressed', c.dataset.value===value));
    } else {
      const set = state[group];
      set.has(value) ? set.delete(value) : set.add(value);
      chip.setAttribute('aria-pressed', set.has(value));
    }
    render(); return;
  }
  const mark = e.target.closest('.mark');
  if(mark){
    const k = mark.closest('.row').dataset.k;
    applied[k] = !applied[k];
    try{ localStorage.setItem('radar-applied', JSON.stringify(applied)); }catch(err){}
    render();
  }
});

document.getElementById('search').addEventListener('input', e => {
  state.q = e.target.value.trim().toLowerCase(); render();
});

render();
"""


def _histogram(history: dict) -> str:
    today = date.today()
    days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    values = [history.get(d, {}).get("new", 0) for d in days]
    peak = max(values) or 1
    bars = []
    for d, v in zip(days, values):
        pct = max(3, round(v / peak * 100))
        cls = "bar today" if d == today.isoformat() else "bar"
        bars.append(f'<div class="{cls}" style="height:{pct}%">'
                    f'<span>{d} · {v} new</span></div>')
    total = sum(values)
    return (f'<div class="detect"><div class="detect-label">'
            f'<span>new postings detected, last 30 days</span>'
            f'<span>{total} total</span></div>'
            f'<div class="bars">{"".join(bars)}</div></div>')


def _chip(group: str, value: str, label: str, count: int | None = None) -> str:
    suffix = f" {count}" if count is not None else ""
    return (f'<button class="chip" data-group="{group}" data-value="{value}" '
            f'aria-pressed="false">{label}{suffix}</button>')


def build(jobs: list[dict], history: dict) -> str:
    today = date.today().isoformat()
    payload = []
    for j in jobs:
        payload.append({
            "key": j["key"],
            "title": j.get("title", ""),
            "company": j.get("company", ""),
            "location": j.get("location", ""),
            "url": j.get("url", ""),
            "region": j.get("region", ""),
            "role_type": j.get("role_type", "full_time"),
            "org_cat": j.get("org_cat", "aggregator"),
            "cat_label": CATEGORIES.get(j.get("org_cat", ""), "other"),
            "relevance": j.get("relevance", 0),
            "match_terms": j.get("match_terms", []),
            "visa_status": j.get("visa_status", "unknown"),
            "visa_reason": j.get("visa_reason", ""),
            "cap_exempt": bool(j.get("cap_exempt")),
            "already_contacted": bool(j.get("already_contacted")),
            "first_seen": j.get("first_seen", today),
            "is_new": j.get("first_seen") == today,
            "source": j.get("source", ""),
            "snippet": (j.get("description") or "")[:340],
        })
    payload.sort(key=lambda x: (-x["relevance"], x["first_seen"]))

    def tally(field):
        out = {}
        for p in payload:
            out[p[field]] = out.get(p[field], 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    new_count = sum(1 for p in payload if p["is_new"])
    exempt_count = sum(1 for p in payload if p["cap_exempt"])
    friendly = sum(1 for p in payload if p["visa_status"] in ("explicit", "likely"))

    type_chips = "".join(
        _chip("type", k, {"full_time": "full time", "new_grad": "new grad",
                          "internship": "internship", "fellowship": "fellowship",
                          "seasonal": "seasonal"}.get(k, k), v)
        for k, v in tally("role_type").items())
    cat_chips = "".join(_chip("cat", k, CATEGORIES.get(k, k), v)
                        for k, v in tally("org_cat").items() if v >= 2)
    visa_chips = "".join(_chip("visa", k, k, v) for k, v in tally("visa_status").items())
    region_chips = "".join(_chip("region", k, k, v)
                           for k, v in list(tally("region").items())[:10])

    generated = datetime.now().strftime("%d %B %Y, %H:%M")

    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head><body>

<header><div class="wrap">
  <div class="stamp">survey run <b>{generated}</b> · rebuilt every morning</div>
  <h1 class="title">Job Radar</h1>
  <p class="sub">Openings across genomics, conservation, marine science, museums,
  science media and policy, read straight off employer career pages and filtered
  for someone graduating in May 2027 on an F-1 visa. The colour down the left of
  each row is the sponsorship read.</p>
  {_histogram(history)}
  <div class="counts">
    <div class="count"><div class="n">{len(payload)}</div><div class="k">open now</div></div>
    <div class="count new"><div class="n">{new_count}</div><div class="k">new today</div></div>
    <div class="count exempt"><div class="n">{exempt_count}</div><div class="k">cap exempt</div></div>
    <div class="count"><div class="n">{friendly}</div><div class="k">F-1 friendly</div></div>
  </div>
</div></header>

<div class="controls"><div class="wrap">
  <input id="search" class="search" type="search" placeholder="filter by title, employer, place or matched term">
  <div class="chips">
    <span class="grouplabel">show</span>
    {_chip("flag", "newOnly", "new today")}
    {_chip("flag", "exemptOnly", "cap exempt only")}
    {_chip("flag", "hideApplied", "hide applied")}
    <span class="grouplabel">sort</span>
    <button class="chip" data-group="sort" data-value="relevance" aria-pressed="true">best fit</button>
    <button class="chip" data-group="sort" data-value="date" aria-pressed="false">newest</button>
  </div>
  <details class="drawer"><summary>filters</summary>
    <div class="drawerbody">
      <div class="chips"><span class="grouplabel">type</span>{type_chips}</div>
      <div class="chips"><span class="grouplabel">F-1</span>{visa_chips}</div>
      <div class="chips"><span class="grouplabel">field</span>{cat_chips}</div>
      <div class="chips"><span class="grouplabel">where</span>{region_chips}</div>
    </div>
  </details>
</div></div>

<main class="wrap">
  <div class="tally mono" id="tally"></div>
  <div id="list"></div>
</main>

<footer><div class="wrap">
  Sponsorship reads are inferred from posting language and employer type, not from
  a verified database. Treat explicit as reliable and everything else as a starting point.<br>
  Cap exempt means the employer is a university, affiliated nonprofit or nonprofit
  research institute and can file an H-1B outside the annual lottery.<br>
  Applied marks are stored in this browser only.
</div></footer>

<script>{JS.replace("__DATA__", json.dumps(payload, ensure_ascii=False))}</script>
</body></html>"""
    return html


def write(jobs: list[dict], history: dict) -> None:
    out_cfg = settings()["output"]
    dash = ROOT / out_cfg["dashboard"]
    feed = ROOT / out_cfg["json_feed"]
    dash.parent.mkdir(parents=True, exist_ok=True)
    dash.write_text(build(jobs, history), encoding="utf-8")
    feed.write_text(json.dumps(jobs, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("wrote %s (%d KB)", dash, len(dash.read_text(encoding="utf-8")) // 1024)
