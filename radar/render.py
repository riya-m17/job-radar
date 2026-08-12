"""Build the dashboard.

Three bands, in the order a job search actually works:

  1. What to do this month, ranked, with the reason attached.
  2. The deadline calendar, because the programmes most likely to work are
     annual and invisible to job boards, and the failure mode is finding one
     in February that closed in November.
  3. The openings ledger, which is discovery rather than action.

Styled as a field survey record rather than a job board: dense rows, a
monospace data column, and a twelve month band showing when application
windows close. The colour down the left edge of every opening is the F-1
verdict, so the page can be triaged without reading a word.
"""

from __future__ import annotations

import json
from datetime import date, datetime

from .util import ROOT, load_config, log, settings

CATEGORIES = load_config("taxonomy")["categories"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CSS = """
:root{
  --ink:#0A1418; --shelf:#101F26; --raise:#16303A; --rule:#1E333D;
  --ice:#DCE8ED; --fog:#7C949F; --dim:#4E6874;
  --kelp:#5FA37E; --glacier:#6FA8C7; --amber:#D9A441; --rust:#C4614F;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--ink);color:var(--ice);
  font-family:'IBM Plex Sans',system-ui,sans-serif;font-size:15px;line-height:1.5;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 22px}
a{color:inherit}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace}

header{border-bottom:1px solid var(--rule);padding:34px 0 26px}
.title{font-family:'Fraunces',Georgia,serif;font-weight:600;
  font-size:clamp(30px,5vw,46px);letter-spacing:-.02em;line-height:1.05;
  font-variation-settings:'SOFT' 40,'WONK' 1}
.sub{color:var(--fog);font-size:13.5px;margin-top:8px;max-width:64ch}
.stamp{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--dim);margin-bottom:12px}
.stamp b{color:var(--glacier);font-weight:500}

.band{border-bottom:1px solid var(--rule);padding:30px 0}
.bandhead{font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);display:flex;justify-content:space-between;
  align-items:baseline;margin-bottom:16px;gap:12px}

.act{display:grid;grid-template-columns:30px 1fr auto;gap:0 14px;
  padding:13px 0;border-top:1px solid var(--rule);align-items:baseline}
.act .n{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--amber)}
.act h3{font-size:15.5px;font-weight:500}
.act h3 a{text-decoration:none;border-bottom:1px solid var(--rule)}
.act h3 a:hover{border-bottom-color:var(--glacier)}
.act .who{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--fog);margin-top:3px}
.act .why{font-size:13px;color:var(--fog);margin-top:7px;max-width:76ch}
.act .when{font-family:'IBM Plex Mono',monospace;font-size:11.5px;text-align:right;white-space:nowrap}
.when.closing{color:var(--rust)}
.when.open{color:var(--kelp)}
.when.upcoming{color:var(--amber)}
.when.year_round{color:var(--dim)}
.when.blocked{color:var(--rust)}
.badge{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.1em;
  padding:2px 6px;border-radius:2px;margin-left:8px;vertical-align:middle;white-space:nowrap}
.badge.eligible{background:#2C5442;color:#8FD3AE}
.badge.unverified{border:1px solid #5A452C;color:#C79A5E}
.badge.ineligible{background:#5A3029;color:#E8A196}
.elig{font-size:12.5px;color:var(--fog);margin-top:7px;max-width:78ch;
  padding-left:11px;border-left:2px solid var(--rule)}

.year{display:flex;align-items:flex-end;gap:4px;height:64px;margin-bottom:8px}
.mo{flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%}
.mo .fill{background:var(--raise);border-radius:1px 1px 0 0;min-height:3px;transition:background .15s}
.mo:hover .fill{background:var(--glacier)}
.mo.now .fill{background:var(--amber)}
.molabel{display:flex;gap:4px;font-family:'IBM Plex Mono',monospace;font-size:10px;
  color:var(--dim);letter-spacing:.06em}
.molabel span{flex:1;text-align:center}
.molabel span.now{color:var(--amber)}

.prog{display:grid;grid-template-columns:1fr auto;gap:0 16px;padding:11px 0;
  border-top:1px solid var(--rule);align-items:baseline}
.prog .nm{font-size:14.5px}
.prog .nm a{text-decoration:none;border-bottom:1px solid var(--rule)}
.prog .nm a:hover{border-bottom-color:var(--glacier)}
.prog .org{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--fog);margin-top:3px}
.prog .st{font-family:'IBM Plex Mono',monospace;font-size:11px;text-align:right;white-space:nowrap}
details.cal summary{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--fog);
  cursor:pointer;list-style:none;border:1px solid var(--rule);padding:5px 10px;
  border-radius:2px;display:inline-block;margin-top:14px}
details.cal summary::-webkit-details-marker{display:none}
details.cal summary:hover{color:var(--ice);border-color:var(--dim)}

.counts{display:flex;flex-wrap:wrap;gap:0}
.count{padding:0 26px 0 0;margin-right:26px;border-right:1px solid var(--rule)}
.count:last-child{border-right:0}
.count .n{font-family:'IBM Plex Mono',monospace;font-size:26px;line-height:1;letter-spacing:-.02em}
.count .k{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-top:6px}
.count.new .n{color:var(--amber)}
.count.exempt .n{color:var(--kelp)}

.controls{position:sticky;top:0;background:var(--ink);z-index:20;
  border-bottom:1px solid var(--rule);padding:14px 0 12px}
.search{width:100%;background:var(--shelf);border:1px solid var(--rule);color:var(--ice);
  font-family:'IBM Plex Mono',monospace;font-size:13px;padding:10px 13px;border-radius:3px}
.search:focus{outline:2px solid var(--glacier);outline-offset:1px;border-color:transparent}
.search::placeholder{color:var(--dim)}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:11px}
.chip{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.04em;
  background:transparent;border:1px solid var(--rule);color:var(--fog);
  padding:5px 10px;border-radius:2px;cursor:pointer;transition:all .12s}
.chip:hover{border-color:var(--dim);color:var(--ice)}
.chip[aria-pressed="true"]{background:var(--glacier);border-color:var(--glacier);
  color:var(--ink);font-weight:500}
.chip:focus-visible{outline:2px solid var(--amber);outline-offset:2px}
.grouplabel{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);align-self:center;margin-right:2px}
details.drawer{margin-top:10px}
details.drawer>summary{font-family:'IBM Plex Mono',monospace;font-size:11px;
  letter-spacing:.06em;color:var(--fog);cursor:pointer;list-style:none;
  display:inline-flex;gap:7px;align-items:center;border:1px solid var(--rule);
  padding:5px 10px;border-radius:2px}
details.drawer>summary::-webkit-details-marker{display:none}
details.drawer>summary:hover{color:var(--ice);border-color:var(--dim)}
details.drawer>summary::after{content:'open';color:var(--dim);font-size:10px}
details.drawer[open]>summary::after{content:'close'}
.drawerbody{max-height:38vh;overflow-y:auto;padding:10px 0 2px;
  border-top:1px solid var(--rule);margin-top:10px}

.tally{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--dim);
  padding:16px 0 8px;letter-spacing:.05em}
.row{display:grid;grid-template-columns:4px 1fr auto;gap:0 16px;
  border-bottom:1px solid var(--rule);align-items:start}
.strip{align-self:stretch;background:var(--dim)}
.strip.explicit{background:var(--kelp)}
.strip.likely{background:var(--glacier)}
.strip.unknown{background:var(--dim)}
.strip.permit{background:#3E5A6B}
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
.startag{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.1em;
  background:var(--kelp);color:var(--ink);padding:2px 6px;border-radius:2px;font-weight:600}
.meta{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--fog);
  margin-top:5px;display:flex;flex-wrap:wrap;gap:4px 12px}
.meta .co{color:var(--ice)}
.meta .fresh{color:var(--kelp)}
.meta .old{color:#B08A4E}
.meta .nodate{color:var(--dim)}
.meta .deadline{color:var(--glacier)}
.meta .urgent{color:var(--rust)}
.urgenttag{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.1em;
  background:var(--rust);color:#fff;padding:2px 6px;border-radius:2px;font-weight:600}
.placetag{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.1em;
  border:1px solid #2A4E60;color:var(--glacier);padding:2px 6px;border-radius:2px}
.oldtag{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.1em;
  border:1px solid #5A452C;color:#C79A5E;padding:2px 6px;border-radius:2px}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}
.tag{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.05em;
  border:1px solid var(--rule);color:var(--fog);padding:2px 7px;border-radius:2px}
.tag.visa-explicit{color:var(--kelp);border-color:#2C5442}
.tag.visa-likely{color:var(--glacier);border-color:#2A4E60}
.tag.visa-blocked{color:var(--rust);border-color:#5A3029}
.tag.visa-unlikely{color:#C79A5E;border-color:#5A452C}
.tag.contact{color:var(--amber);border-color:#5A4720}
.tag.skill{color:var(--kelp);border-color:#2C5442}
.tag.exp-ok{color:var(--kelp);border-color:#2C5442}
.tag.exp-stretch{color:#C79A5E;border-color:#5A452C}
.tag.flav{color:var(--glacier);border-color:#2A4E60}
.phdtag{font-family:'IBM Plex Mono',monospace;font-size:9.5px;letter-spacing:.1em;
  border:1px solid #5A452C;color:#C79A5E;padding:2px 6px;border-radius:2px}
.side{padding:15px 0;text-align:right;display:flex;flex-direction:column;
  align-items:flex-end;gap:7px;min-width:104px}
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
  .act{grid-template-columns:22px 1fr}
  .act .when{grid-column:2;text-align:left;margin-top:6px}
  .count{padding-right:18px;margin-right:18px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = """
const DATA = __DATA__;
const state = {q:'', type:new Set(), cat:new Set(), visa:new Set(), region:new Set(),
               fresh:new Set(), exp:new Set(), place:new Set(), flav:new Set(),
               newOnly:false, verifiedOnly:false,
               exemptOnly:false, starOnly:false, closingOnly:false,
               hideApplied:false, hideUndated:false, sort:'best'};
let applied = {};
try{ applied = JSON.parse(localStorage.getItem('radar-applied')||'{}'); }catch(e){}

const esc = s => (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const TYPE_LABEL = {full_time:'full time', new_grad:'new grad', internship:'internship',
                    fellowship:'fellowship', seasonal:'seasonal'};

function dateLine(j){
  if(j.posted_confidence === 'unknown') return 'no date published';
  const d = j.age_days;
  const ago = d <= 0 ? 'today' : d === 1 ? 'yesterday' : d + 'd ago';
  return 'opened ' + (j.posted_confidence === 'approximate' ? '~' : '') + ago;
}

function closeLine(j){
  if(j.closes_kind === 'stated'){
    const n = j.closes_in_days;
    const when = n <= 0 ? 'closes today' : n === 1 ? 'closes tomorrow'
               : 'closes in ' + n + 'd';
    return '<span class="'+(j.closing_soon?'urgent':'deadline')+'">'+when+
           ' &middot; ' + j.closes_date + '</span>';
  }
  if(j.closes_kind === 'rolling') return '<span class="nodate">rolling, apply early</span>';
  return '<span class="nodate">no deadline stated</span>';
}

const PLACE_LABEL = {west_coast:'WEST COAST', copenhagen:'COPENHAGEN', india:'INDIA'};

function matches(j){
  if(state.newOnly && !j.is_new) return false;
  if(state.exemptOnly && !j.cap_exempt) return false;
  if(state.starOnly && !j.has_signature) return false;
  if(state.hideApplied && applied[j.key]) return false;
  if(state.type.size && !state.type.has(j.role_type)) return false;
  if(state.cat.size && !state.cat.has(j.org_cat)) return false;
  if(state.visa.size && !state.visa.has(j.visa_status)) return false;
  if(state.region.size && !state.region.has(j.region)) return false;
  if(state.fresh.size && !state.fresh.has(j.freshness)) return false;
  if(state.exp.size && !state.exp.has(j.experience_verdict)) return false;
  if(state.place.size && !state.place.has(j.priority_place)) return false;
  if(state.closingOnly && !j.closing_soon) return false;
  if(state.flav.size && !(j.flavours||[]).some(f => state.flav.has(f))) return false;
  if(state.verifiedOnly && j.link_state !== 'alive') return false;
  if(state.hideUndated && j.posted_confidence === 'unknown') return false;
  if(state.q){
    const hay = (j.title+' '+j.company+' '+j.location+' '+
                 (j.skill_hits||[]).join(' ')+' '+(j.match_terms||[]).join(' ')).toLowerCase();
    if(!state.q.split(/\\s+/).every(t => hay.includes(t))) return false;
  }
  return true;
}

// Undated postings sort as if they were a month old: not hidden, but never
// allowed to sit above something with a real recent date on it.
const ageOf = j => j.posted_confidence === 'unknown' ? 30 : j.age_days;
const SORTS = {
  fit:   (a,b) => b.total_score-a.total_score,
  skill: (a,b) => b.skill_score-a.skill_score || b.total_score-a.total_score,
  date:  (a,b) => ageOf(a)-ageOf(b) || b.total_score-a.total_score,
  // Fit and fresh, but a stated deadline inside a fortnight jumps the queue,
  // because a good match you can no longer apply to is worth nothing.
  best:  (a,b) => (b.closing_soon?1:0)-(a.closing_soon?1:0)
                  || (ageOf(a)-ageOf(b))*0.6 - (a.total_score-b.total_score),
  closes:(a,b) => (a.closes_in_days==null?9999:a.closes_in_days)
                  - (b.closes_in_days==null?9999:b.closes_in_days)
};

function render(){
  const rows = DATA.filter(matches).sort(SORTS[state.sort]);
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
    const skills = (j.skill_hits||[]).slice(0,4)
      .map(t=>'<span class="tag skill">'+esc(t)+'</span>').join('');
    const overlap = (j.skill_hits||[]).length
      ? 'your overlap: '+esc((j.skill_hits||[]).join(', '))
      : 'no direct skill overlap found in the posting text';
    return '<article class="row'+done+'" data-k="'+j.key+'">'+
      '<div class="strip '+j.visa_status.replace('/','')+'"></div>'+
      '<div class="body">'+
        '<div class="rowtop">'+
          '<h2 class="jtitle"><a href="'+esc(j.url)+'" target="_blank" rel="noopener">'+esc(j.title)+'</a></h2>'+
          (j.is_new?'<span class="newtag">NEW</span>':'')+
          (j.has_signature?'<span class="startag">YOUR NICHE</span>':'')+
          (j.freshness==='ageing'?'<span class="oldtag">'+j.age_days+'D OLD</span>':'')+
          (j.closing_soon?'<span class="urgenttag">CLOSING</span>':'')+
          (j.priority_place?'<span class="placetag">'+PLACE_LABEL[j.priority_place]+'</span>':'')+
          (j.phd_pipeline?'<span class="phdtag">PHD PIPELINE</span>':'')+
        '</div>'+
        '<div class="meta"><span class="co">'+esc(j.company)+'</span>'+
          '<span>'+esc(j.location||j.region||'location not stated')+'</span>'+
          '<span class="'+(j.freshness==='ageing'?'old':j.freshness==='undated'?'nodate':'fresh')+'">'+
            dateLine(j)+'</span>'+closeLine(j)+'</div>'+
        '<div class="tags">'+
          '<span class="tag visa-'+j.visa_status.replace('/','')+'">F-1 '+esc(j.visa_status)+'</span>'+
          '<span class="tag">'+esc(TYPE_LABEL[j.role_type]||j.role_type)+'</span>'+
          '<span class="tag">'+esc(j.cat_label)+'</span>'+
          (j.cap_exempt?'<span class="tag visa-likely">cap exempt</span>':'')+
          (j.already_contacted?'<span class="tag contact">already contacted</span>':'')+
          (j.years_required!==null&&j.years_required!==undefined
            ?'<span class="tag '+(j.experience_verdict==='stretch'?'exp-stretch':'exp-ok')+'">'+
              j.years_required+'y experience</span>':'')+
          (j.flavours||[]).filter(f=>f!=='other').map(f=>
            '<span class="tag flav">'+esc(f)+'</span>').join('')+
          skills+
        '</div>'+
        '<details class="more"><summary>why this surfaced</summary><div class="detail">'+
          '<div class="why">F-1 read: '+esc(j.visa_reason)+'</div>'+
          '<div class="why" style="margin-top:6px">'+overlap+'</div>'+
          (j.snippet?'<p style="margin-top:8px">'+esc(j.snippet)+'</p>':'')+
          '<div class="why" style="margin-top:6px">experience: '+esc(j.experience_detail)+'</div>'+
          '<div class="why">topic '+j.relevance+', skill '+j.skill_score+
          ', date '+esc(j.posted_confidence)+
          (j.posted_date?' ('+esc(j.posted_date)+')':'')+
          ', source '+esc(j.source)+'</div>'+
        '</div></details>'+
      '</div>'+
      '<div class="side"><span class="score">fit '+j.total_score+'</span>'+
        '<button class="mark" aria-pressed="'+(applied[j.key]?'true':'false')+'">'+
        (applied[j.key]?'applied':'mark applied')+'</button></div>'+
    '</article>';
  }).join('');
}

document.addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if(chip){
    const group = chip.dataset.group, value = chip.dataset.value;
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


def _badge(p: dict) -> str:
    st = p.get("status", "unverified")
    label = {"eligible": "VERIFIED", "unverified": "UNVERIFIED",
             "ineligible": "NOT ELIGIBLE"}[st]
    return '<span class="badge ' + st + '">' + label + '</span>'


def _checked(p: dict) -> str:
    return " &middot; checked " + p["checked"] if p.get("checked") else ""


def _elig(p: dict) -> str:
    text = " ".join((p.get("eligibility") or "").split())
    return '<div class="elig">' + text + '</div>' if text else ""


def _state_label(p: dict) -> tuple[str, str]:
    d, s = p["days"], p["state"]
    if s == "blocked":
        return "blocked", "not eligible"
    if p.get("has_exact_deadline") and s in ("closing", "open"):
        return s, "due " + p["ref_date"]
    if s == "closing":
        return s, f"closes in {d}d"
    if s == "open":
        return s, f"open, {d}d left"
    if s == "upcoming":
        return s, f"opens in {max(1, round(d / 7))}w"
    return s, "rolling"


def _act_now_band(calendar: list[dict]) -> str:
    from . import programs as prog_mod
    picks = prog_mod.act_now(calendar)
    if not picks:
        return ""
    rows = []
    for i, p in enumerate(picks, 1):
        cls, label = _state_label(p)
        note = " ".join((p.get("note") or "").split())
        rows.append(
            f'<div class="act"><div class="n">{i:02d}</div><div>'
            f'<h3><a href="{p["url"]}" target="_blank" rel="noopener">{p["name"]}</a>'
            f'{_badge(p)}</h3>'
            f'<div class="who">{p["org"]} &middot; {p.get("type", "")} &middot; '
            f'about {p.get("effort", "?")}h to apply{_checked(p)}</div>'
            f'{_elig(p)}'
            f'<p class="why">{note}</p></div>'
            f'<div class="when {cls}">{label}</div></div>')
    return ('<section class="band"><div class="wrap">'
            '<div class="bandhead"><span>what to do this month</span>'
            '<span>verified first, dead ends excluded</span></div>'
            f'{"".join(rows)}</div></section>')


def _calendar_band(calendar: list[dict]) -> str:
    if not calendar:
        return ""
    now = date.today().month
    per_month = [0] * 12
    for p in calendar:
        if p["state"] != "year_round":
            per_month[int(p["closes"]) - 1] += 1
    peak = max(per_month) or 1

    bars, labels = [], []
    for i, n in enumerate(per_month):
        cls = "mo now" if i + 1 == now else "mo"
        height = max(4, round(n / peak * 100))
        bars.append(f'<div class="{cls}" title="{MONTHS[i]}: {n} closing">'
                    f'<div class="fill" style="height:{height}%"></div></div>')
        labels.append(f'<span class="{"now" if i + 1 == now else ""}">{MONTHS[i]}</span>')

    rows = []
    for p in calendar:
        cls, label = _state_label(p)
        rows.append(
            f'<div class="prog"><div>'
            f'<div class="nm"><a href="{p["url"]}" target="_blank" rel="noopener">{p["name"]}</a>{_badge(p)}</div>'
            f'<div class="org">{p["org"]} &middot; {p.get("type", "")}</div></div>'
            f'<div class="st {cls}">{label}</div></div>')

    return ('<section class="band"><div class="wrap">'
            '<div class="bandhead"><span>application windows closing, by month</span>'
            f'<span>{len(calendar)} programmes tracked</span></div>'
            f'<div class="year">{"".join(bars)}</div>'
            f'<div class="molabel">{"".join(labels)}</div>'
            f'<details class="cal"><summary>all {len(calendar)} programmes</summary>'
            f'{"".join(rows)}</details></div></section>')


def _chip(group: str, value: str, label: str, count: int | None = None) -> str:
    suffix = f" {count}" if count is not None else ""
    return (f'<button class="chip" data-group="{group}" data-value="{value}" '
            f'aria-pressed="false">{label}{suffix}</button>')


def _health_band() -> str:
    """Show how much of the employer registry actually resolved.

    The registry was written from my own knowledge and is imperfect. The only
    real evidence about which entries exist is whether a live board answers,
    so that evidence belongs on the page rather than buried in a log.
    """
    path = ROOT / "data" / "registry_health.json"
    if not path.exists():
        return ""
    try:
        h = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return ""

    total = h.get("registry_size", 0) or 1
    res = len(h.get("resolved", []))
    quar = h.get("quarantined_no_public_feed", [])
    retry = h.get("missing_retrying", [])
    empty = h.get("resolved_but_no_open_roles", [])
    pct = round(100 * res / total)

    def listing(title, names):
        if not names:
            return ""
        shown = ", ".join(names[:60])
        more = f" and {len(names) - 60} more" if len(names) > 60 else ""
        return (f'<details class="cal"><summary>{title} ({len(names)})</summary>'
                f'<p class="why" style="margin-top:10px">{shown}{more}</p></details> ')

    return ('<section class="band"><div class="wrap">'
            '<div class="bandhead"><span>employer registry coverage</span>'
            f'<span>{res} of {total} resolved &middot; {pct}%</span></div>'
            '<p class="why" style="max-width:78ch;margin-bottom:12px">'
            'Resolved means a live public job feed was found and read. '
            'Quarantined means repeated runs found none, so the employer is '
            'either on a system with no public API such as Workday, or is in '
            'the registry under a name that does not match reality. Prune those '
            'from config/organizations.yaml, or replace the hint with the '
            'correct board slug.</p>'
            + listing("quarantined, no public feed", quar)
            + listing("not resolved this run, retrying", retry)
            + listing("resolved but no open roles today", empty)
            + '</div></section>')


def build(jobs: list[dict], history: dict, calendar: list[dict] | None = None) -> str:
    calendar = calendar or []
    today = date.today().isoformat()
    payload = []
    for j in jobs:
        payload.append({
            "key": j["key"], "title": j.get("title", ""), "company": j.get("company", ""),
            "location": j.get("location", ""), "url": j.get("url", ""),
            "region": j.get("region", ""), "role_type": j.get("role_type", "full_time"),
            "org_cat": j.get("org_cat", "aggregator"),
            "cat_label": CATEGORIES.get(j.get("org_cat", ""), "other"),
            "relevance": j.get("relevance", 0),
            "skill_score": j.get("skill_score", 0),
            "total_score": j.get("total_score", j.get("relevance", 0)),
            "skill_hits": j.get("skill_hits", []),
            "has_signature": bool(j.get("has_signature")),
            "match_terms": j.get("match_terms", []),
            "visa_status": j.get("visa_status", "unknown"),
            "visa_reason": j.get("visa_reason", ""),
            "cap_exempt": bool(j.get("cap_exempt")),
            "already_contacted": bool(j.get("already_contacted")),
            "first_seen": j.get("first_seen", today),
            "is_new": j.get("first_seen") == today,
            "posted_date": j.get("posted_date"),
            "posted_confidence": j.get("posted_confidence", "unknown"),
            "age_days": j.get("age_days", 0),
            "freshness": j.get("freshness", "undated"),
            "closes_date": j.get("closes_date"),
            "closes_kind": j.get("closes_kind", "none"),
            "closes_in_days": j.get("closes_in_days"),
            "closing_soon": bool(j.get("closing_soon")),
            "priority_place": j.get("priority_place", ""),
            "flavours": j.get("flavours", []),
            "phd_pipeline": bool(j.get("phd_pipeline_flavour")),
            "link_state": j.get("link_state", "unknown"),
            "experience_verdict": j.get("experience_verdict", "unstated"),
            "experience_detail": j.get("experience_detail", ""),
            "years_required": j.get("years_required"),
            "source": j.get("source", ""),
            "snippet": (j.get("description") or "")[:340],
        })
    payload.sort(key=lambda x: -x["total_score"])

    def tally(field):
        out = {}
        for p in payload:
            out[p[field]] = out.get(p[field], 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    new_count = sum(1 for p in payload if p["is_new"])
    exempt_count = sum(1 for p in payload if p["cap_exempt"])
    niche_count = sum(1 for p in payload if p["has_signature"])
    week_count = sum(1 for p in payload if p["freshness"] == "this week")
    closing_count = sum(1 for p in payload if p["closing_soon"])
    priority_count = sum(1 for p in payload if p["priority_place"])
    nonbench_count = sum(1 for p in payload
                         if set(p["flavours"]) - {"bench", "other"})

    labels = {"full_time": "full time", "new_grad": "new grad",
              "internship": "internship", "fellowship": "fellowship",
              "seasonal": "seasonal"}
    type_chips = "".join(_chip("type", k, labels.get(k, k), v)
                         for k, v in tally("role_type").items())
    fresh_order = ["this week", "recent", "ageing", "undated"]
    fresh_counts = tally("freshness")
    fresh_chips = "".join(_chip("fresh", k, k, fresh_counts[k])
                          for k in fresh_order if k in fresh_counts)
    exp_order = ["new grad ok", "unstated", "stretch"]
    exp_counts = tally("experience_verdict")
    exp_chips = "".join(_chip("exp", k, k, exp_counts[k])
                        for k in exp_order if k in exp_counts)
    place_labels = {"west_coast": "west coast", "copenhagen": "Copenhagen",
                    "india": "India"}
    flav_counts = {}
    for p in payload:
        for f in p["flavours"]:
            if f != "other":
                flav_counts[f] = flav_counts.get(f, 0) + 1
    flav_order = ["computational", "bench", "commercial", "creative", "comms", "field"]
    flav_chips = "".join(_chip("flav", f, f, flav_counts[f])
                         for f in flav_order if flav_counts.get(f))
    place_counts = tally("priority_place")
    place_chips = "".join(_chip("place", k, place_labels[k], place_counts[k])
                          for k in ("west_coast", "copenhagen", "india")
                          if place_counts.get(k))
    cat_chips = "".join(_chip("cat", k, CATEGORIES.get(k, k), v)
                        for k, v in tally("org_cat").items() if v >= 2)
    visa_chips = "".join(_chip("visa", k, k, v) for k, v in tally("visa_status").items())
    region_chips = "".join(_chip("region", k, k, v)
                           for k, v in list(tally("region").items())[:10])

    generated = datetime.now().strftime("%d %B %Y, %H:%M")
    data_json = json.dumps(payload, ensure_ascii=False)

    return f"""<!doctype html>
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
  <div class="stamp">survey run <b>{generated}</b> &middot; rebuilt every morning</div>
  <h1 class="title">Job Radar</h1>
  <p class="sub">Openings across genomics, conservation, marine science, museums,
  consulting, science media and policy, read straight off employer career pages,
  scored against what you can already do, and filtered for someone graduating in
  May 2027 on an F-1 visa. The colour down the left of each row is the
  sponsorship read.</p>
</div></header>

{_act_now_band(calendar)}
{_calendar_band(calendar)}
{_health_band()}

<section class="band"><div class="wrap"><div class="counts">
  <div class="count"><div class="n">{len(payload)}</div><div class="k">open now</div></div>
  <div class="count new"><div class="n">{new_count}</div><div class="k">new today</div></div>
  <div class="count exempt"><div class="n">{exempt_count}</div><div class="k">cap exempt</div></div>
  <div class="count"><div class="n">{niche_count}</div><div class="k">your niche</div></div>
  <div class="count"><div class="n">{week_count}</div><div class="k">opened this week</div></div>
  <div class="count"><div class="n">{closing_count}</div><div class="k">closing in 14d</div></div>
  <div class="count"><div class="n">{priority_count}</div><div class="k">where you want</div></div>
  <div class="count"><div class="n">{nonbench_count}</div><div class="k">not bench work</div></div>
</div></div></section>

<div class="controls"><div class="wrap">
  <input id="search" class="search" type="search" placeholder="filter by title, employer, place or matched skill">
  <div class="chips">
    <span class="grouplabel">show</span>
    {_chip("flag", "newOnly", "new today")}
    {_chip("flag", "starOnly", "your niche only")}
    {_chip("flag", "exemptOnly", "cap exempt only")}
    {_chip("flag", "hideApplied", "hide applied")}
    {_chip("flag", "hideUndated", "hide undated")}
    {_chip("flag", "closingOnly", "closing within 14d")}
    {_chip("flag", "verifiedOnly", "link verified live")}
    <span class="grouplabel">sort</span>
    <button class="chip" data-group="sort" data-value="best" aria-pressed="true">fit and fresh</button>
    <button class="chip" data-group="sort" data-value="date" aria-pressed="false">newest</button>
    <button class="chip" data-group="sort" data-value="closes" aria-pressed="false">closing soonest</button>
    <button class="chip" data-group="sort" data-value="fit" aria-pressed="false">best fit</button>
    <button class="chip" data-group="sort" data-value="skill" aria-pressed="false">skill overlap</button>
  </div>
  <details class="drawer"><summary>filters</summary>
    <div class="drawerbody">
      <div class="chips"><span class="grouplabel">kind of work</span>{flav_chips}</div>
      <div class="chips"><span class="grouplabel">where you want</span>{place_chips}</div>
      <div class="chips"><span class="grouplabel">posted</span>{fresh_chips}</div>
      <div class="chips"><span class="grouplabel">experience</span>{exp_chips}</div>
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
  Calendar entries marked VERIFIED were read off the programme's own page on the date
  shown, including eligibility rules. UNVERIFIED entries are unchecked guesses, so
  confirm before relying on them. NOT ELIGIBLE entries are kept deliberately so a dead
  end is not rediscovered later, and are never surfaced as something to act on.<br>
  Sponsorship reads are inferred from posting language and employer type, not a verified
  database. Treat explicit as reliable and everything else as a question to ask.<br>
  Cap exempt means a university, affiliated nonprofit or nonprofit research institute,
  which can file an H-1B outside the annual lottery.<br>
  Permit means a role outside the US: no F-1 question, but a local work permit is still
  needed and the posting says nothing about supporting one.<br>
  Closing dates are only shown when the employer states one. Nothing is inferred
  from the posting date, so "no deadline stated" means exactly that.<br>
  Every posting link is fetched and the ones that are provably gone, whether a 404,
  a redirect to a careers index, or a page saying the role is closed, are removed
  rather than shown.<br>
  Roles requiring that you intend to pursue a PhD are dropped. Postings that merely
  describe themselves as a route to graduate school are kept and tagged.<br>
  Roles asking for more than two years of experience, a doctorate, or bench work
  in a named professor's university laboratory are removed. The employer stays in
  the registry either way, so it is still watched for roles you could actually get.<br>
  Posting dates come from the employer's own system where possible. A tilde means
  the date came from a feed and is roughly right; no date published means the board
  does not publish one, and those never rank as fresh. Anything the employer dated
  more than 75 days ago is dropped, and roles requiring citizenship, permanent
  residence or a clearance are removed rather than shown.<br>
  Skill overlap is matched against config/profile.yaml. Applied marks live in this browser only.
</div></footer>

<script>{JS.replace("__DATA__", data_json)}</script>
</body></html>"""


def write(jobs: list[dict], history: dict, calendar: list[dict] | None = None) -> None:
    out_cfg = settings()["output"]
    dash = ROOT / out_cfg["dashboard"]
    feed = ROOT / out_cfg["json_feed"]
    dash.parent.mkdir(parents=True, exist_ok=True)
    dash.write_text(build(jobs, history, calendar), encoding="utf-8")
    feed.write_text(json.dumps(jobs, indent=1, ensure_ascii=False), encoding="utf-8")
    log.info("wrote %s (%d KB)", dash, len(dash.read_text(encoding="utf-8")) // 1024)
