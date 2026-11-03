"""공개 전략 페이지 /data — 검색엔진·AI가 읽어 갈 서버 렌더링 HTML (docs/seo/기획.md).

  /data/                 허브 — 무엇인지·분야·최근 전략
  /data/s/{id}           전략 사례 — 질문 → 한 문단 답 → 전략 본문 → 데이터 → 포털 AI 비교 → 지금 물어보기 → 관련 전략
  /data/d/{id}           데이터 사전 — 실측 필드·호출 방법·검증 결과·조인·이 데이터를 쓰는 전략
  /data/t/{분야}[/{쪽}]  분야 허브 — 분야의 전략·데이터
  /sitemap.xml           사이트맵 색인 → /data/sitemap-{hubs|strategies|datasets-N}.xml
  /data/llms.txt         AI용 목차 (전략 질문 전부) · /data/rss.xml 최근 전략 100 (네이버 서치어드바이저)
재료는 seo/strategies.json(python -m pds.seo.build)과 지식 색인. 페이지는 처음 요청 때 그려 메모리에 둔다.
'지금 물어보기'는 메인 화면 /?q=…&ref=seo 로 보내 그 자리에서 전략을 다시 만든다 (rel=nofollow — 검색엔진이 따라가 색인하지 않게).
"""
from __future__ import annotations

import html
import json
import os
import re
from functools import lru_cache
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from pds import config

router = APIRouter(include_in_schema=False)
SRC = config.ROOT / "seo" / "strategies.json"
SITE = "공공데이터 전략 도우미"
PER_PAGE = 200
SITEMAP_MAX = 40000
ROLE = {"primary": "대표", "join": "연결", "aligned": "단위 맞춤", "context": "참고", "support": "보조"}
KIND = {"API": "오픈API", "FILE": "파일", "EXTERNAL_API": "외부 사이트 API", "EXTERNAL_FILE": "외부 사이트 파일", "STD": "표준데이터"}
TYPE = {"lookup": "찾기", "combine": "엮기", "region": "지역", "analysis": "분석", "casual": "생활 질문"}
PRIVATE = re.compile(r"전화|연락처|휴대|핸드폰|팩스|이메일|메일|email|e-mail|tel|phone|fax|성명|이름|담당자|대표자|작성자|주민", re.I)


def _base(req: Request) -> str:
    return (os.environ.get("PDS_PUBLIC_URL") or str(req.base_url)).rstrip("/")


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def _short(title: str) -> str:
    return re.sub(r"^[^_]{2,30}_", "", title or "")


# ─────────────────────────── 재료
class Store:
    def __init__(self) -> None:
        j = json.loads(SRC.read_text(encoding="utf-8")) if SRC.exists() else {"strategies": [], "datasets": []}
        self.built = j.get("built")
        self.strategies = {p["id"]: p for p in j["strategies"]}
        self.ds_pages = set(j["datasets"])
        self.by_ds: dict[str, list[str]] = {}
        for p in j["strategies"]:
            for i in dict.fromkeys([d["id"] for d in p["datasets"]] + p.get("cited", [])):
                self.by_ds.setdefault(i, []).append(p["id"])
        self.sectors: dict[str, list[str]] = {}
        for p in j["strategies"]:
            self.sectors.setdefault(p["sector"], []).append(p["id"])
        from pds.service import index
        ix = index.get()
        self.ds_sector: dict[str, list[str]] = {}
        for i in sorted(self.ds_pages):
            d = ix.datasets.get(i)
            if d:
                self.ds_sector.setdefault((d.get("sector") or "기타").split("/")[0], []).append(i)
        for s in self.ds_sector:
            self.ds_sector[s].sort(key=lambda i: -(((ix.datasets[i].get("verification") or {}).get("rows")) or 0))


@lru_cache(maxsize=1)
def store() -> Store:
    return Store()


def reload() -> None:
    store.cache_clear()
    _render.cache_clear()


# ─────────────────────────── 틀
CSS = """
:root{--bg:#fafafa;--card:#fff;--fg:#17171c;--mut:#62626e;--line:#e6e6ea;--acc:#2456d6;--acc-bg:#eef3ff;--ok:#127a3d;--warn:#a15c00}
@media (prefers-color-scheme:dark){:root{--bg:#111114;--card:#1a1a1f;--fg:#ececf1;--mut:#a0a0ab;--line:#2b2b33;--acc:#86a8ff;--acc-bg:#1d2540;--ok:#5bd38a;--warn:#f0b35a}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 Pretendard,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;word-break:keep-all;overflow-wrap:anywhere}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
.top{border-bottom:1px solid var(--line);background:var(--card)}.top div{max-width:880px;margin:0 auto;padding:12px 16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.top b{font-size:15px}.top a.app{margin-left:auto;font-size:14px}
main{max-width:880px;margin:0 auto;padding:20px 16px 72px}
nav.bc{font-size:13px;color:var(--mut)}nav.bc a{color:var(--mut)}
h1{font-size:26px;line-height:1.4;margin:10px 0 6px}h2{font-size:19px;margin:36px 0 10px}h3{font-size:16px;margin:22px 0 6px}
.meta{font-size:13px;color:var(--mut)}.lead{font-size:17px;background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:8px;padding:14px 16px;margin:16px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.answer ul,.answer ol{padding-left:22px}.answer p{margin:8px 0}.answer strong{font-weight:700}
.wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card);border:1px solid var(--line);border-radius:8px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{color:var(--mut);font-weight:600;font-size:12.5px;white-space:nowrap}
td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}code{font-size:13px;background:var(--acc-bg);padding:1px 5px;border-radius:4px}
.chip{display:inline-block;font-size:12px;border:1px solid var(--line);border-radius:999px;padding:1px 8px;color:var(--mut);margin-right:4px}
.cta{background:var(--acc-bg);border:1px solid var(--line);border-radius:12px;padding:16px;margin:28px 0}
.cta a.go{display:inline-block;background:var(--acc);color:#fff;padding:9px 16px;border-radius:8px;font-weight:600;margin:6px 0}
@media (prefers-color-scheme:dark){.cta a.go{color:#0d1020}}
.cta ul{margin:8px 0 0;padding-left:20px}.cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.cmp div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}.cmp b{font-size:20px;display:block}
.list li{margin:6px 0}.foot{border-top:1px solid var(--line);margin-top:48px;padding-top:16px;font-size:13px;color:var(--mut)}
.pager{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.pager a,.pager span{border:1px solid var(--line);border-radius:6px;padding:2px 9px;font-size:14px}
"""


def _verify_meta() -> str:
    out = []
    if os.environ.get("PDS_GOOGLE_SITE_VERIFICATION"):
        out.append(f'<meta name="google-site-verification" content="{_e(os.environ["PDS_GOOGLE_SITE_VERIFICATION"])}">')
    if os.environ.get("PDS_NAVER_SITE_VERIFICATION"):
        out.append(f'<meta name="naver-site-verification" content="{_e(os.environ["PDS_NAVER_SITE_VERIFICATION"])}">')
    return "".join(out)


def _ga() -> str:
    gid = os.environ.get("PDS_GA4_WEB_ID") or os.environ.get("GA4_MEASUREMENT_ID")
    if not gid:
        return ""
    return (f'<script async src="https://www.googletagmanager.com/gtag/js?id={_e(gid)}"></script>'
            f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','{_e(gid)}');</script>")


def _doc(base: str, path: str, title: str, desc: str, body: str, ld: list[dict] | None = None, crumbs: list[tuple[str, str]] | None = None) -> str:
    url = base + path
    crumbs = crumbs or []
    lds = list(ld or [])
    if crumbs:
        lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList",
                    "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": base + p} for i, (n, p) in enumerate(crumbs)]})
    bc = " › ".join(f'<a href="{_e(p)}">{_e(n)}</a>' for n, p in crumbs[:-1]) if len(crumbs) > 1 else ""
    ldj = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in lds)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><meta name="description" content="{_e(desc[:155])}"><link rel="canonical" href="{_e(url)}">
<meta property="og:type" content="article"><meta property="og:title" content="{_e(title)}"><meta property="og:description" content="{_e(desc[:155])}">
<meta property="og:url" content="{_e(url)}"><meta property="og:site_name" content="{SITE}"><meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary">{_verify_meta()}<link rel="icon" href="/favicon.ico"><style>{CSS}</style>{ldj}{_ga()}</head>
<body><header class="top"><div><b><a href="/data/">{SITE} · 공공데이터 전략 사례</a></b><a class="app" href="/">질문하러 가기 →</a></div></header>
<main>{f'<nav class="bc" aria-label="위치">{bc}</nav>' if bc else ''}{body}
<div class="foot">이 페이지는 data.go.kr 공공데이터 7만여 건을 실제로 호출해 실측한 지식 체계로 만든 전략입니다. 데이터·수치는 실측·검증 기록에서만 가져옵니다.
· <a href="/data/">전략 사례 목차</a> · <a href="/">질문하기</a> · <a href="/#/mcp">MCP 연결</a> · <a href="https://github.com/kloud80/datagokr-mcp">GitHub</a></div></main></body></html>"""


def _ask(q: str) -> str:
    return f"/?q={quote(q)}&ref=seo"


def _md(text: str, s: Store) -> str:
    from markdown_it import MarkdownIt
    from pds.service import index
    ix = index.get()

    def lk(m):
        i = m.group(1)
        if i in s.ds_pages:
            return f"[{_short(ix.datasets[i]['title']) if i in ix.datasets else i}](/data/d/{i})"
        return f"[포털 {i}](https://www.data.go.kr/data/{i}/openapi.do)"
    return MarkdownIt("commonmark", {"html": False}).enable("table").render(re.sub(r"\[\[(\d+)\]\]", lk, text or ""))


def _first_para(reply: str) -> str:
    """한 문단 답 — 답 첫머리를 평문으로 (스니펫·AI 요약용)."""
    t = re.sub(r"\[\[(\d+)\]\]", "", reply or "")
    t = re.sub(r"[*#`>]+", "", t)
    lines = [x.strip(" -·") for x in t.splitlines() if x.strip(" -·")]
    out = ""
    for x in lines:
        if len(out) > 160:
            break
        out += (" " if out else "") + x.rstrip(":")
    return re.sub(r"\s+", " ", out)[:300]


# ─────────────────────────── 전략 사례
def strategy_page(base: str, sid: str) -> str:
    s = store()
    p = s.strategies.get(sid)
    if not p:
        raise HTTPException(404)
    from pds.service import index
    ix = index.get()
    lead = _first_para(p["reply"])
    rows = []
    for d in p["datasets"]:
        dd = ix.datasets.get(d["id"]) or {}
        name = f'<a href="/data/d/{d["id"]}">{_e(d["title"])}</a>' if d["id"] in s.ds_pages else _e(d["title"])
        rows.append(f"<tr><td>{name}</td><td>{_e((dd.get('agency') or {}).get('name'))}</td><td>{_e(KIND.get(dd.get('kind'), dd.get('kind')))}</td>"
                    f"<td>{_e(ROLE.get(d.get('role'), d.get('role')))}</td></tr>")
    leads = "".join(f'<li><a href="https://www.data.go.kr/data/{_e(x["id"])}/openapi.do" rel="nofollow">{_e(x["title"])}</a> — 검증 전 단서, 포털에서 확인</li>'
                    for x in p.get("leads") or [])
    cmp = ""
    c = p.get("compare")
    if c:
        cmp = f"""<h2>공공데이터포털 AI 검색과 비교</h2>
<p>같은 질문을 공공데이터포털 AI 검색에도 물어 두 답을 출처를 가린 채 비교했습니다(판정: Claude Opus, {p.get('date')}).</p>
<div class="cmp"><div><span class="meta">핵심 데이터 수</span><b>{c['ours_core']} · {c['portal_core']}</b><span class="meta">이 전략 · 포털</span></div>
<div><span class="meta">답 점수 (20점)</span><b>{c['ours_score']} · {c['portal_score']}</b><span class="meta">관련성·포괄·실행·정직성 합</span></div></div>
{f'<p><b>포털 답에 없던 것</b>: {_e(c["portal_missing"])}</p>' if c.get("portal_missing") else ''}
<p class="meta">판정도 언어모델이 해 편향이 있을 수 있습니다. 1천 문항 전체 결과는 <a href="https://github.com/kloud80/datagokr-mcp/tree/main/evals/portal_1k">평가 기록</a>에 있습니다.</p>"""
    gaps = "".join(f"<li>{_e(g)}</li>" for g in p.get("gaps") or [])
    variants = "".join(f'<li><a href="{_e(_ask(v))}" rel="nofollow">{_e(v)}</a></li>' for v in p.get("variants") or [])
    related = "".join(f'<li><a href="/data/s/{r}">{_e(s.strategies[r]["q"])}</a></li>' for r in p.get("related") or [] if r in s.strategies)
    title = f"{p['q']} — 공공데이터 전략"
    desc = f"{lead}"
    ld = [{"@context": "https://schema.org", "@type": "QAPage", "mainEntity": {
        "@type": "Question", "name": p["q"], "text": p["q"], "answerCount": 1, "dateCreated": p.get("date"),
        "author": {"@type": "Organization", "name": SITE},
        "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"\[\[(\d+)\]\]", r"(데이터 \1)", p["reply"])[:5000], "dateCreated": p.get("date"),
                           "url": base + f"/data/s/{sid}", "author": {"@type": "Organization", "name": SITE}}}},
          {"@context": "https://schema.org", "@type": "TechArticle", "headline": p["q"][:110], "inLanguage": "ko", "datePublished": p.get("date"),
           "about": [{"@type": "Dataset", "name": d["title"], "url": base + f"/data/d/{d['id']}"} for d in p["datasets"] if d["id"] in s.ds_pages][:10],
           "publisher": {"@type": "Organization", "name": "BigValue"}}]
    body = f"""<h1>{_e(p['q'])}</h1>
<div class="meta"><span class="chip">{_e(p['sector'])}</span><span class="chip">{_e(TYPE.get(p['type'], p['type']))}</span>답 생성 {_e(p.get('date'))} · 데이터 {len(p['datasets'])}개 · 조인 {p.get('joins') or 0}개</div>
<p class="lead">{_e(lead)}</p>
<div class="cta"><b>내 조건으로 다시 받아 보세요</b> — 지역·기간·단위를 바꿔 물으면 데이터 조합·조인·실행 코드를 새로 만듭니다.<br>
<a class="go" href="{_e(_ask(p['q']))}" rel="nofollow">이 질문으로 지금 전략 받기</a></div>
<h2>전략</h2><div class="card answer">{_md(p['reply'], s)}</div>
<h2>쓰는 데이터</h2><div class="wrap"><table><tr><th>데이터</th><th>기관</th><th>유형</th><th>역할</th></tr>{''.join(rows)}</table></div>
{f'<h3>직접 확인할 단서</h3><ul class="list">{leads}</ul>' if leads else ''}
{f'<h3>채우지 못한 부분</h3><ul class="list">{gaps}</ul>' if gaps else ''}
{cmp}
<div class="cta"><b>비슷한 질문으로 물어보기</b><ul>{variants}</ul></div>
{f'<h2>관련 전략</h2><ul class="list">{related}</ul>' if related else ''}"""
    crumbs = [("전략 사례", "/data/"), (p["sector"], f"/data/t/{quote(p['sector'])}"), (p["q"][:40], f"/data/s/{sid}")]
    return _doc(base, f"/data/s/{sid}", title, desc, body, ld, crumbs)


# ─────────────────────────── 데이터 사전
def dataset_page(base: str, did: str) -> str:
    s = store()
    from pds.service import index
    ix = index.get()
    d = ix.datasets.get(did)
    if not d or did not in s.ds_pages:
        raise HTTPException(404)
    v = d.get("verification") or {}
    ag = (d.get("agency") or {}).get("name") or ""
    sector = (d.get("sector") or "기타").split("/")[0]
    fields = (d.get("schema") or {}).get("fields") or []
    frows = []
    for f in fields[:120]:
        st = f.get("stats") or {}
        priv = PRIVATE.search(f"{f.get('name')} {f.get('title')}")
        smp = "" if priv else ", ".join(str(x)[:30] for x in (f.get("sample_values") or [])[:2])
        nr = f.get("null_rate")
        frows.append(f"<tr><td><code>{_e(f.get('name'))}</code></td><td>{_e(f.get('title'))}</td><td>{_e(f.get('type'))}</td>"
                     f"<td class=n>{'' if nr is None else f'{nr * 100:.0f}%'}</td><td class=n>{_e(st.get('unique', ''))}</td><td>{_e(smp)}</td></tr>")
    svc = []
    for x in (d.get("services") or [])[:6]:
        ps = ", ".join(f"{p.get('name')}{'*' if p.get('required') else ''}" for p in (x.get("params") or [])[:12] if isinstance(p, dict))
        svc.append(f"<tr><td>{_e(x.get('name') or x.get('op'))}</td><td><code>{_e(x.get('endpoint'))}</code></td><td>{_e(ps)}</td></tr>")
    sec = ((d.get("services") or [{}])[0].get("security") or {}) if d.get("services") else {}
    key = {"data.go.kr": "data.go.kr 활용신청 후 받은 serviceKey"}.get(sec.get("issuer"), f"{sec.get('issuer')} 발급 키" if sec.get("issuer") else "")
    edges = []
    for e in ix.edges:
        if did not in (e["src"], e["dst"]) or e["rel"] == "related_to":
            continue
        o = e["dst"] if e["src"] == did else e["src"]
        od = ix.datasets.get(o)
        name = (f'<a href="/data/d/{o}">{_e(od["title"])}</a>' if o in s.ds_pages else _e(od["title"])) if od else _e(o)
        on = e.get("on") or {}
        mr = (e.get("verified") or {}).get("match_rate")
        edges.append(f"<tr><td>{name}</td><td><code>{_e(','.join(on.get('left') or []))}</code> = <code>{_e(','.join(on.get('right') or []))}</code></td>"
                     f"<td>{_e(e['rel'])}</td><td class=n>{'' if mr is None else f'{mr * 100:.1f}%'}</td></tr>")
        if len(edges) >= 20:
            break
    used = "".join(f'<li><a href="/data/s/{sid}">{_e(s.strategies[sid]["q"])}</a></li>' for sid in s.by_ds.get(did, [])[:12] if sid in s.strategies)
    cov = d.get("coverage") or {}
    summary = d.get("summary_user") or d.get("description_portal") or ""
    short = _short(d["title"])
    asks = [f"{short} 데이터로 무엇을 분석할 수 있어?", f"{short}와 함께 엮으면 좋은 공공데이터는?", f"{short} 데이터를 파이썬으로 받는 코드 알려줘"]
    title = f"{d['title']} — 필드·호출 방법·실측 결과"
    desc = f"{ag} {short}: {KIND.get(d.get('kind'), d.get('kind'))}. 필드 {len(fields)}개, 실측 {v.get('rows') or '-'}행. {summary}"
    ld = [{"@context": "https://schema.org", "@type": "Dataset", "name": d["title"], "description": (summary or d["title"])[:4900] + (" " * max(0, 50 - len(summary))),
           "url": base + f"/data/d/{did}", "sameAs": d.get("portal_url"), "creator": {"@type": "Organization", "name": ag or "공공기관"},
           "inLanguage": "ko", "isAccessibleForFree": True, "keywords": (d.get("synonyms") or [])[:12],
           "spatialCoverage": cov.get("spatial"), "temporalCoverage": (cov.get("temporal") or "").replace(" ~ ", "/") or None,
           "variableMeasured": [f.get("title") or f.get("name") for f in fields[:40]],
           "distribution": [{"@type": "DataDownload", "contentUrl": d.get("portal_url"), "encodingFormat": "application/json" if "API" in (d.get("kind") or "") else "text/csv"}]
           if d.get("portal_url") else None}]
    ld[0] = {k: x for k, x in ld[0].items() if x not in (None, [], "")}
    body = f"""<h1>{_e(d['title'])}</h1>
<div class="meta"><span class="chip">{_e(sector)}</span><span class="chip">{_e(KIND.get(d.get('kind'), d.get('kind')))}</span>{_e(ag)}{f" · 검증 {_e(v.get('probed_at'))}" if v.get('probed_at') else ''}</div>
<p class="lead">{_e(summary[:600])}</p>
<h2>한눈에</h2><div class="wrap"><table>
<tr><th>제공 기관</th><td>{_e(ag)}</td></tr><tr><th>유형</th><td>{_e(KIND.get(d.get('kind'), d.get('kind')))} · {'data.go.kr' if d.get('channel') == 'portal' else '외부 사이트'}</td></tr>
<tr><th>범위</th><td>{_e(cov.get('spatial'))} {_e(cov.get('admin_unit'))} {_e(cov.get('temporal'))}</td></tr>
<tr><th>실측</th><td>{f"{v.get('rows'):,}행 받음" if isinstance(v.get('rows'), int) else '-'}{f" · 최신 데이터 {_e(v.get('latest'))}" if v.get('latest') else ''}{f" · 오퍼레이션 {_e(v.get('ops_ok'))} 성공" if v.get('ops_ok') else ''}</td></tr>
{f"<tr><th>필요한 키</th><td>{_e(key)}</td></tr>" if key else ''}
<tr><th>원본</th><td>{f'<a href="{_e(d.get("portal_url"))}" rel="nofollow">{_e(d.get("portal_url"))}</a>' if d.get('portal_url') else '-'}</td></tr></table></div>
{f'<h2>호출 방법</h2><div class="wrap"><table><tr><th>오퍼레이션</th><th>주소</th><th>인자 (*필수)</th></tr>{"".join(svc)}</table></div>' if svc else ''}
{f'<p class="meta">{_e(d.get("limits"))}</p>' if d.get('limits') else ''}
<h2>필드 ({len(fields)}개, 실측)</h2>
<div class="wrap"><table><tr><th>이름</th><th>뜻</th><th>타입</th><th>빈 값</th><th>고유값</th><th>표본</th></tr>{''.join(frows) or '<tr><td colspan=6>필드 실측 없음</td></tr>'}</table></div>
{f'<h2>이어 쓸 수 있는 데이터</h2><div class="wrap"><table><tr><th>데이터</th><th>잇는 키</th><th>관계</th><th>실측 매칭률</th></tr>{"".join(edges)}</table></div>' if edges else ''}
{f'<h2>이 데이터를 쓰는 전략</h2><ul class="list">{used}</ul>' if used else ''}
<div class="cta"><b>이 데이터로 물어보기</b><ul>{"".join(f'<li><a href="{_e(_ask(a))}" rel="nofollow">{_e(a)}</a></li>' for a in asks)}</ul></div>"""
    crumbs = [("전략 사례", "/data/"), (sector, f"/data/t/{quote(sector)}"), (short[:40], f"/data/d/{did}")]
    return _doc(base, f"/data/d/{did}", title, desc, body, ld, crumbs)


# ─────────────────────────── 허브
def sector_page(base: str, sector: str, page: int = 1) -> str:
    s = store()
    sids = s.sectors.get(sector, [])
    dids = s.ds_sector.get(sector, [])
    if not sids and not dids:
        raise HTTPException(404)
    from pds.service import index
    ix = index.get()
    n = max(1, -(-len(dids) // PER_PAGE))
    if page < 1 or page > n:
        raise HTTPException(404)
    strat = "".join(f'<li><a href="/data/s/{i}">{_e(s.strategies[i]["q"])}</a></li>' for i in sids) if page == 1 else ""
    ds = "".join(f'<li><a href="/data/d/{i}">{_e(ix.datasets[i]["title"])}</a> <span class="meta">{_e(KIND.get(ix.datasets[i].get("kind"), ""))}</span></li>'
                 for i in dids[(page - 1) * PER_PAGE: page * PER_PAGE])
    pager = "".join(f'<span>{k}</span>' if k == page else f'<a href="/data/t/{quote(sector)}{"" if k == 1 else f"/{k}"}">{k}</a>' for k in range(1, n + 1)) if n > 1 else ""
    path = f"/data/t/{quote(sector)}" + ("" if page == 1 else f"/{page}")
    body = f"""<h1>{_e(sector)} 공공데이터 전략{'' if page == 1 else f' ({page}쪽)'}</h1>
<p class="lead">{_e(sector)} 분야에서 공공데이터로 답한 질문 {len(sids)}개와, 실제로 호출해 필드를 실측한 데이터 {len(dids):,}개입니다.</p>
{f'<h2>질문별 전략</h2><ul class="list">{strat}</ul>' if strat else ''}
{f'<h2>데이터 사전</h2><ul class="list">{ds}</ul><div class="pager">{pager}</div>' if ds else ''}
<div class="cta"><b>{_e(sector)} 데이터로 하고 싶은 일이 있나요?</b><br><a class="go" href="/" >질문하러 가기</a></div>"""
    return _doc(base, path, f"{sector} 공공데이터 전략·데이터 사전" + ("" if page == 1 else f" {page}쪽"),
                f"{sector} 분야 공공데이터 활용 전략 {len(sids)}개와 실측 데이터 사전 {len(dids):,}개 — 어떤 데이터를 어떻게 이어 쓰는지.", body,
                crumbs=[("전략 사례", "/data/"), (sector, path)])


def home_page(base: str) -> str:
    s = store()
    secs = sorted(set(s.sectors) | set(s.ds_sector), key=lambda x: -(len(s.sectors.get(x, [])) * 100 + len(s.ds_sector.get(x, []))))
    sec = "".join(f'<li><a href="/data/t/{quote(x)}">{_e(x)}</a> <span class="meta">전략 {len(s.sectors.get(x, []))} · 데이터 {len(s.ds_sector.get(x, [])):,}</span></li>' for x in secs)
    pick = [p for p in s.strategies.values() if (p.get("compare") or {}).get("ours_core", 0) - (p.get("compare") or {}).get("portal_core", 0) >= 3][:30]
    pick += [p for p in s.strategies.values() if not p.get("compare")][:20]
    best = "".join(f'<li><a href="/data/s/{p["id"]}">{_e(p["q"])}</a></li>' for p in pick)
    body = f"""<h1>공공데이터 전략 사례</h1>
<p class="lead">"이 일을 하려면 어떤 공공데이터를, 어떻게 이어서 써야 하나?"에 대한 답 {len(s.strategies)}개와, data.go.kr 데이터를 실제로 호출해 필드를 실측한 데이터 사전 {len(s.ds_pages):,}개입니다.
공공데이터포털 검색이 "무엇이 있는가"를 찾아 준다면, 이 사례들은 <b>무엇을 왜 고르고, 어떤 키로 잇고, 무엇이 없는지</b>까지 알려 줍니다.</p>
<div class="cta"><b>내 질문으로 바로 받아 보기</b> — 지역·기간·대상을 적어 물으면 검증된 데이터 조합·조인 경로·실행 코드를 만듭니다.<br><a class="go" href="/">질문하러 가기</a>
 <a href="/#/mcp">· Claude·ChatGPT 등에 MCP로 연결하기</a></div>
<h2>분야별</h2><ul class="list">{sec}</ul>
<h2>포털 AI 검색보다 크게 앞선 전략</h2><ul class="list">{best}</ul>
<h2>어떻게 만들었나</h2><p>data.go.kr과 연계 사이트의 공공데이터를 실제로 활용신청하고 호출해 행과 필드를 실측했습니다(검증 74,505건).
데이터끼리 잇는 방법은 미리 선언하고 실제 데이터로 매칭률을 쟀습니다(조인 30,435개). 같은 질문 1,000개로 공공데이터포털 AI 검색과 비교하면
앞에 내놓은 5개 중 핵심 데이터 비율이 42%(포털 29%), 무관 데이터는 9%(포털 28%)였습니다. 자세한 내용은 <a href="https://github.com/kloud80/datagokr-mcp">GitHub</a>에 있습니다.</p>"""
    ld = [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "공공데이터 전략 사례", "inLanguage": "ko", "url": base + "/data/",
           "description": "공공데이터를 목표에 맞게 고르고 잇는 전략 사례와 실측 데이터 사전"}]
    return _doc(base, "/data/", "공공데이터 전략 사례 — 어떤 데이터를 어떻게 이어 쓸까", "공공데이터로 하고 싶은 일마다 어떤 데이터를 왜 고르고 어떤 키로 잇는지, "
                f"실제 호출로 검증한 전략 {len(s.strategies)}개와 데이터 사전 {len(s.ds_pages):,}개.", body, ld, [("전략 사례", "/data/")])


@lru_cache(maxsize=4096)
def _render(kind: str, base: str, key: str, page: int = 1) -> str:
    if kind == "s":
        return strategy_page(base, key)
    if kind == "d":
        return dataset_page(base, key)
    if kind == "t":
        return sector_page(base, key, page)
    return home_page(base)


def _html(text: str) -> HTMLResponse:
    return HTMLResponse(text, headers={"cache-control": "public, max-age=3600"})


@router.get("/data", response_class=HTMLResponse)
@router.get("/data/", response_class=HTMLResponse)
def r_home(req: Request):
    return _html(_render("h", _base(req), ""))


@router.get("/data/s/{sid}", response_class=HTMLResponse)
def r_strategy(sid: str, req: Request):
    return _html(_render("s", _base(req), sid))


@router.get("/data/d/{did}", response_class=HTMLResponse)
def r_dataset(did: str, req: Request):
    return _html(_render("d", _base(req), did))


@router.get("/data/t/{sector}", response_class=HTMLResponse)
def r_sector(sector: str, req: Request):
    return _html(_render("t", _base(req), sector))


@router.get("/data/t/{sector}/{page}", response_class=HTMLResponse)
def r_sector_page(sector: str, page: int, req: Request):
    return _html(_render("t", _base(req), sector, page))


# ─────────────────────────── 사이트맵 · AI 목차
def urls(base: str) -> dict[str, list[tuple[str, str | None]]]:
    s = store()
    hubs = [(base + "/data/", (s.built or "")[:10] or None), (base + "/", None)]
    for x in set(s.sectors) | set(s.ds_sector):
        n = max(1, -(-len(s.ds_sector.get(x, [])) // PER_PAGE))
        hubs += [(base + f"/data/t/{quote(x)}" + ("" if k == 1 else f"/{k}"), None) for k in range(1, n + 1)]
    strat = [(base + f"/data/s/{p['id']}", p.get("date")) for p in s.strategies.values()]
    from pds.service import index
    ix = index.get()
    ds = [(base + f"/data/d/{i}", ((ix.datasets.get(i) or {}).get("verification") or {}).get("probed_at")) for i in sorted(s.ds_pages)]
    out = {"hubs": hubs, "strategies": strat}
    for k in range(0, len(ds), SITEMAP_MAX):
        out[f"datasets-{k // SITEMAP_MAX + 1}"] = ds[k:k + SITEMAP_MAX]
    return out


def _xml(body: str) -> Response:
    return Response('<?xml version="1.0" encoding="UTF-8"?>\n' + body, media_type="application/xml", headers={"cache-control": "public, max-age=3600"})


@router.get("/sitemap.xml")
def r_sitemap(req: Request):
    b = _base(req)
    items = "".join(f"<sitemap><loc>{_e(b)}/data/sitemap-{k}.xml</loc></sitemap>" for k in urls(b))
    return _xml(f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</sitemapindex>')


@router.get("/data/sitemap-{name}.xml")
def r_sitemap_part(name: str, req: Request):
    u = urls(_base(req)).get(name)
    if u is None:
        raise HTTPException(404)
    items = "".join(f"<url><loc>{_e(loc)}</loc>{f'<lastmod>{_e(lm)}</lastmod>' if lm else ''}</url>" for loc, lm in u)
    return _xml(f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>')


@router.get("/data/rss.xml")
def r_rss(req: Request):
    """RSS — 네이버 서치어드바이저가 새 글을 찾는 통로. 최근 전략 100개."""
    s, b = store(), _base(req)
    ps = sorted(s.strategies.values(), key=lambda p: (p.get("date") or "", p["id"]), reverse=True)[:100]
    items = []
    for p in ps:
        pub = f"<pubDate>{_rfc822(p['date'])}</pubDate>" if p.get("date") else ""
        items.append(f"<item><title>{_e(p['q'])}</title><link>{_e(b)}/data/s/{p['id']}</link><guid>{_e(b)}/data/s/{p['id']}</guid>"
                     f"<description>{_e(_first_para(p['reply']))}</description><category>{_e(p['sector'])}</category>{pub}</item>")
    items = "".join(items)
    return _xml(f'<rss version="2.0"><channel><title>{SITE} — 공공데이터 전략 사례</title><link>{_e(b)}/data/</link>'
                f"<description>공공데이터로 하고 싶은 일마다 어떤 데이터를 어떻게 이어 쓰는지 — 실측 근거 전략</description><language>ko</language>{items}</channel></rss>")


def _rfc822(day: str) -> str:
    import datetime as dt
    from email.utils import format_datetime
    return format_datetime(dt.datetime.fromisoformat(day).replace(hour=9, tzinfo=dt.timezone(dt.timedelta(hours=9))))


@router.get("/data/llms.txt", response_class=PlainTextResponse)
def r_llms(req: Request):
    s, b = store(), _base(req)
    lines = [f"# {SITE} — 공공데이터 전략 사례", "",
             "공공데이터로 하고 싶은 일마다 어떤 데이터를 왜 고르고, 어떤 키로 잇고, 무엇이 없는지를 실측 근거로 답한 페이지 목록.",
             f"새 질문은 {b}/?q=질문 (사람) 또는 MCP {b}/mcp · REST POST {b}/api/plan (에이전트).", ""]
    for sec, ids in sorted(s.sectors.items(), key=lambda x: -len(x[1])):
        lines += [f"## {sec}", *[f"- [{s.strategies[i]['q']}]({b}/data/s/{i})" for i in ids], ""]
    return PlainTextResponse("\n".join(lines))


# ─────────────────────────── IndexNow (빙·네이버·얀덱스 …)
@router.get("/{key}.txt", response_class=PlainTextResponse)
def r_indexnow_key(key: str):
    k = os.environ.get("PDS_INDEXNOW_KEY", "")
    if not k or key != k:
        raise HTTPException(404)
    return PlainTextResponse(k)
