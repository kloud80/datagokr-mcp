"""사용 현황 — logs/usage/*.jsonl을 모아 사용자 수·사용량을 본다 (GET /admin/usage, 이 컴퓨터에서만).

사용자 = client_hash (IP·브라우저를 소금 친 해시 — 같은 사람이 다른 기기·IP로 오면 다르게 센다).
내 컴퓨터·내부망에서 온 호출은 usage.LOCAL_FILE에 해시를 모아 두고(기록할 때부터) 기본으로 뺀다 — ?local=1이면 넣는다.
그 기록을 남기기 전에 쌓인 로컬 호출(개발·시험)은 가려낼 수 없어 섞여 있다.
날짜는 한국 시간.
"""
from __future__ import annotations

import ast
import datetime as dt
import html
import json
from collections import Counter, defaultdict

from pds.service.usage import LOG_DIR, local_hashes

KST = dt.timezone(dt.timedelta(hours=9))


def _obj(v):
    if isinstance(v, (dict, list)) or v is None:
        return v
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return None


def load(include_local: bool = False) -> list[dict]:
    loc = local_hashes()
    rs = []
    for f in sorted(LOG_DIR.glob("*.jsonl")):
        for line in f.open(encoding="utf-8"):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            r["_local"] = r.get("client_hash") in loc
            if r["_local"] and not include_local:
                continue
            r["_t"] = dt.datetime.fromisoformat(r["at"]).astimezone(KST)
            rs.append(r)
    return rs


def stats(include_local: bool = False) -> dict:
    rs = load(include_local)
    if not rs:
        return {"total": 0}
    users = defaultdict(lambda: {"calls": 0, "kinds": Counter(), "first": None, "last": None, "days": set()})
    days = defaultdict(lambda: {"users": set(), "new": 0, **{k: 0 for k in ("chat", "mcp", "plan", "feedback")}})
    seen: set[str] = set()
    tools, tokens = Counter(), Counter()
    for r in rs:
        h, d = r.get("client_hash") or "?", r["_t"].date().isoformat()
        u = users[h]
        u["calls"] += 1
        u["kinds"][r["kind"]] += 1
        u["first"] = u["first"] or r["_t"]
        u["last"] = r["_t"]
        u["days"].add(d)
        day = days[d]
        day["users"].add(h)
        day[r["kind"]] = day.get(r["kind"], 0) + 1
        if h not in seen:
            seen.add(h)
            day["new"] += 1
        if r["kind"] == "mcp":
            tools[r.get("question") or "?"] += 1
        if r["kind"] == "chat":
            us = _obj(r.get("usage")) or {}
            for k in ("input", "output", "calls"):
                tokens[k] += int(us.get(k) or 0)
    now = dt.datetime.now(KST)
    active = lambda n: len({r.get("client_hash") for r in rs if r["_t"] >= now - dt.timedelta(days=n)})  # noqa: E731
    chats = [r for r in rs if r["kind"] == "chat"]
    fb = [r for r in rs if r["kind"] == "feedback"]
    return {
        "total": len(rs), "users": len(users), "first": rs[0]["_t"], "last": rs[-1]["_t"],
        "kinds": Counter(r["kind"] for r in rs), "active": {"1일": active(1), "7일": active(7), "30일": active(30)},
        "returning": sum(1 for u in users.values() if len(u["days"]) > 1),
        "sessions": len({r.get("session") for r in chats if r.get("session")}),
        "seo": sum(1 for r in chats if (_obj(r.get("args")) or {}).get("ref") == "seo"),
        "days": [{"day": d, "users": len(v["users"]), "new": v["new"], **{k: v[k] for k in ("chat", "mcp", "plan", "feedback")}}
                 for d, v in sorted(days.items(), reverse=True)],
        "tools": tools.most_common(), "tokens": dict(tokens),
        "errors": sum(1 for r in rs if (r.get("status") not in (None, "ok")) or r.get("error") not in (None, "None", "")),
        "users_top": sorted(({"hash": h, "calls": u["calls"], "kinds": dict(u["kinds"]), "first": u["first"], "last": u["last"],
                              "days": len(u["days"])} for h, u in users.items()), key=lambda x: -x["calls"])[:30],
        "chats": [{"t": r["_t"], "q": r.get("question"), "status": r.get("status"), "s": r.get("elapsed_s"), "user": r.get("client_hash"),
                   "n": len((_obj(r.get("plan_ids")) or {}).get("datasets") or [])} for r in reversed(chats[-50:])],
        "feedback": [{"t": r["_t"], **(_obj(r.get("args")) or {}), "turn": r.get("turn_id")} for r in reversed(fb)],
        "include_local": include_local, "local_users": len(local_hashes()),
    }


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _ts(t) -> str:
    return t.strftime("%m-%d %H:%M") if t else ""


def page(include_local: bool = False) -> str:
    s = stats(include_local)
    css = """
:root{--bg:#f7f7f8;--card:#fff;--fg:#1b1b1f;--mut:#6b6b76;--line:#e4e4e8;--acc:#2f6fed;--acc2:#16a34a;--bar:#c9d8fb}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--card:#1c1c20;--fg:#ececf0;--mut:#9a9aa6;--line:#2c2c33;--acc:#7aa2ff;--acc2:#4ade80;--bar:#2c3d66}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 Pretendard,system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px}
.mut{color:var(--mut)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}
.k{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.k b{display:block;font-size:24px;font-variant-numeric:tabular-nums}
.k span{color:var(--mut);font-size:12px}table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-weight:600;color:var(--mut);font-size:12px}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}
.bar{display:inline-block;height:8px;background:var(--acc);border-radius:4px;vertical-align:middle;margin-right:6px}
code{font-size:12px;color:var(--mut)}a{color:var(--acc)}.up{color:var(--acc2)}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:760px){.two{grid-template-columns:1fr}}"""
    if not s["total"]:
        return f"<!doctype html><meta charset=utf-8><title>사용 현황</title><style>{css}</style><main><h1>사용 현황</h1><p class=mut>기록이 없습니다.</p></main>"
    k = s["kinds"]
    cards = [("사용자(누적)", s["users"]), ("최근 7일 사용자", s["active"]["7일"]), ("최근 1일 사용자", s["active"]["1일"]),
             ("다시 온 사용자", s["returning"]), ("전체 호출", s["total"]), ("채팅 답", k.get("chat", 0)),
             ("MCP 도구 호출", k.get("mcp", 0)), ("REST 전략", k.get("plan", 0)), ("채팅 세션", s["sessions"]),
             ("피드백", k.get("feedback", 0)), ("전략 사례 → 채팅", s["seo"]), ("채팅 토큰(입력)", f"{s['tokens'].get('input', 0):,}"), ("채팅 토큰(출력)", f"{s['tokens'].get('output', 0):,}")]
    mx = max(d["users"] for d in s["days"]) or 1
    days = "".join(f"<tr><td>{d['day']}</td><td class=n><span class=bar style='width:{d['users'] / mx * 80:.0f}px'></span>{d['users']}</td>"
                   f"<td class=n>{d['new']}</td><td class=n>{d['chat']}</td><td class=n>{d['mcp']}</td><td class=n>{d['plan']}</td><td class=n>{d['feedback']}</td></tr>"
                   for d in s["days"])
    tm = s["tools"][0][1] if s["tools"] else 1
    tools = "".join(f"<tr><td><code>{_e(t)}</code></td><td class=n><span class=bar style='width:{n / tm * 80:.0f}px'></span>{n}</td></tr>" for t, n in s["tools"])
    users = "".join(f"<tr><td><code>{_e(u['hash'])}</code></td><td class=n>{u['calls']}</td><td>{_e(' · '.join(f'{a} {b}' for a, b in u['kinds'].items()))}</td>"
                    f"<td class=n>{u['days']}</td><td>{_ts(u['first'])}</td><td>{_ts(u['last'])}</td></tr>" for u in s["users_top"])
    chats = "".join(f"<tr><td>{_ts(c['t'])}</td><td>{_e(c['q'])}</td><td class=n>{c['n']}</td><td class=n>{_e(c['s'])}</td>"
                    f"<td>{'' if c['status'] == 'ok' else _e(c['status'])}</td><td><code>{_e(c['user'])}</code></td></tr>" for c in s["chats"])
    fb = "".join(f"<tr><td>{_ts(f['t'])}</td><td class='{'up' if f.get('rating') == 'up' else ''}'>{'👍' if f.get('rating') == 'up' else '👎'}</td>"
                 f"<td>{_e(f.get('comment'))}</td></tr>" for f in s["feedback"]) or "<tr><td colspan=3 class=mut>없음</td></tr>"
    toggle = ("<a href='?'>내 컴퓨터·내부망 호출 빼고 보기</a>" if s["include_local"] else "<a href='?local=1'>내 컴퓨터·내부망 호출도 넣어 보기</a>")
    return f"""<!doctype html><html lang=ko><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>사용 현황</title><style>{css}</style><main>
<h1>사용 현황</h1>
<div class=mut>{_ts(s['first'])} ~ {_ts(s['last'])} (한국 시간) · 기록 {s['total']:,}건 · {'내 컴퓨터·내부망 호출 포함' if s['include_local'] else f"내 컴퓨터·내부망 사용자 {s['local_users']}명 제외"} · {toggle} · <a href='/admin/usage.json{'?local=1' if s['include_local'] else ''}'>JSON</a></div>
<div class=grid>{''.join(f"<div class=k><b>{_e(v)}</b><span>{_e(n)}</span></div>" for n, v in cards)}</div>
<p class=mut>사용자는 IP·브라우저 해시로 센다 — 같은 사람이 다른 기기·IP로 오면 따로 센다. 로컬 표시는 기록을 시작한 뒤부터라, 그 전에 이 컴퓨터에서 시험한 호출은 섞여 있다.</p>
<h2>날짜별</h2><div class=wrap><table><tr><th>날짜</th><th class=n>사용자</th><th class=n>신규</th><th class=n>채팅</th><th class=n>MCP</th><th class=n>REST</th><th class=n>피드백</th></tr>{days}</table></div>
<div class=two><div><h2>MCP 도구별 호출</h2><table><tr><th>도구</th><th class=n>호출</th></tr>{tools or "<tr><td colspan=2 class=mut>없음</td></tr>"}</table></div>
<div><h2>피드백</h2><table><tr><th>때</th><th></th><th>의견</th></tr>{fb}</table></div></div>
<h2>사용자별 (상위 30)</h2><div class=wrap><table><tr><th>사용자</th><th class=n>호출</th><th>종류</th><th class=n>온 날</th><th>처음</th><th>마지막</th></tr>{users}</table></div>
<h2>최근 채팅 질문 (50)</h2><div class=wrap><table><tr><th>때</th><th>질문</th><th class=n>데이터</th><th class=n>초</th><th>상태</th><th>사용자</th></tr>{chats}</table></div>
</main></html>"""
