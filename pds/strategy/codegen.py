"""코드 생성 (BUILD-PLAN Phase 5 미리보기) — 전략 응답 → 실행 가능한 Python. LLM 없이 결정적으로 만든다.

키는 환경변수에서 읽는다: 포털 DATA_GO_KR_SERVICE_KEY, 외부 사이트 PDS_KEY_{발급처}. 조인은 전략 응답의 joins(선언된 Edge)만 쓴다.
변환 규칙(R-02·R-07·R-12·R-13·R-14)이 걸린 조인은 pds.rules 함수를 부른다 (이 리포를 설치했을 때 — 아니면 주석의 설명대로 구현).
"""
from __future__ import annotations

import re


def _var(i: str) -> str:
    return "df_" + re.sub(r"\W", "_", i)


def _env_key(access: dict) -> str:
    iss = (access or {}).get("issuer") or "data.go.kr"
    return "DATA_GO_KR_SERVICE_KEY" if iss == "data.go.kr" else "PDS_KEY_" + re.sub(r"\W", "_", iss).upper()


def render(p: dict) -> str:
    L = ['"""' + f"자동 생성 — 목표: {p['goal']}", f"지식 버전 {p.get('knowledge_version')} · 조인은 선언된 Edge만 사용", '"""',
         "import os", "import httpx", "import pandas as pd", "", "",
         "def fetch(url, params, key_env, key_name='serviceKey', key_in='query', page='pageNo', size='numOfRows', max_pages=50):",
         "    key = os.environ[key_env]",
         "    rows, n = [], 1",
         "    while n <= max_pages:",
         "        q = dict(params)",
         "        if key_in == 'query':",
         "            q[key_name] = key",
         "        if page:",
         "            q[page], q[size] = n, 1000",
         "        q.setdefault('type', 'json'); q.setdefault('_type', 'json'); q.setdefault('resultType', 'json')",
         "        r = httpx.get(url.replace('{KEY}', key), params=q, timeout=60)",
         "        r.raise_for_status()",
         "        j = r.json()",
         "        items = _items(j)",
         "        if not items:",
         "            break",
         "        rows += items",
         "        if not page or len(items) < 1000:",
         "            break",
         "        n += 1",
         "    return pd.DataFrame(rows)", "", "",
         "def _items(o):",
         "    \"\"\"포털 JSON의 흔한 모양(response.body.items.item / data / row …)에서 행 목록을 찾는다. 오류도 HTTP 200으로 올 수 있다.\"\"\"",
         "    if isinstance(o, list):",
         "        return o if o and isinstance(o[0], dict) else []",
         "    if isinstance(o, dict):",
         "        for k in ('item', 'items', 'data', 'list', 'row', 'body', 'response'):",
         "            if k in o:",
         "                v = o[k]",
         "                if k in ('item', 'row') and isinstance(v, dict) and all(not isinstance(x, (dict, list)) for x in v.values()):",
         "                    return [v]",
         "                got = _items(v)",
         "                if got:",
         "                    return got",
         "        for v in o.values():",
         "            got = _items(v)",
         "            if got:",
         "                return got",
         "    return []", "", ""]
    for d in p["datasets"]:
        f, a = d.get("fetch") or {}, d.get("access") or {}
        L.append(f"# [{d['role']}] {d['id']} {d['title']}")
        if f.get("kind") == "file" or not f.get("endpoint"):
            L.append(f"# 파일 데이터 — 포털에서 내려받아 읽는다: {d.get('portal_url')}")
            L.append(f"{_var(d['id'])} = pd.read_csv('{d['id']}.csv', encoding='utf-8-sig')  # 내려받은 파일 경로로 바꿀 것")
        else:
            scheme = (a.get("scheme") or "apiKey:query:serviceKey").split(":")
            paging = f.get("paging") or {}
            params = {k: v for k, v in (f.get("params") or {}).items() if k not in (paging.get("page"), paging.get("size"))}
            L.append(f"{_var(d['id'])} = fetch({f['endpoint']!r}, {params!r}, {_env_key(a)!r}, key_name={scheme[-1]!r}, "
                     f"key_in={scheme[1] if len(scheme) > 1 else 'query'!r}, page={paging.get('page')!r}, size={paging.get('size') or 'numOfRows'!r})")
        L.append("")
    if p["joins"]:
        L.append("# ── 조인 (선언된 Edge)")
    for j in p["joins"]:
        lv, rv = _var(j["left"]), _var(j["right"])
        on = j["on"]
        t = on.get("transform")
        L.append(f"# {j['edge']} {j['rel']} {j['left']} → {j['right']}" + (f" · 허브 {j['hub']}" if j.get("hub") else "")
                 + (f" · 매핑 {j['via_mapping']}" if j.get("via_mapping") else "")
                 + (f" · 실측 매칭 {j['match_rate']:.0%}" if j.get("match_rate") is not None else ""))
        if j.get("hub"):
            if t == "R-12":
                L.append(f"# 좌표 → PNU: from pds.rules import coord_to_pnu  ({lv}[['위도','경도']] 행마다 호출, 브이월드 키 필요)")
            elif t == "R-13":
                L.append("# 주소 → 좌표 → PNU: from pds.rules import address_to_coord, coord_to_pnu (브이월드 키 필요)")
            elif t == "R-14":
                L.append(f"# 행정구역 이름 → 코드: from pds.rules import admin_name_to_code; {lv}['sgg_cd'] = {lv}[{(on.get('left') or ['시군구명'])[0]!r}].map(admin_name_to_code)")
            else:
                L.append(f"# 법정동·시군구 코드로 지역 단위 결합 (R-02: 시군구 = 법정동 앞 5자리) — 다른 데이터와 같은 코드 열로 groupby 후 merge")
            continue
        if j.get("via_mapping"):
            L.append(f"m = pd.read_parquet('knowledge/mappings/{j['via_mapping']}.parquet')  # left_value → right_value")
            L.append(f"{lv} = {lv}.merge(m[m.right_value.notna()], left_on={on['left'][0]!r}, right_on='left_value', how='left')")
            L.append(f"{lv} = {lv}.merge({rv}, left_on='right_value', right_on={on['right'][0]!r}, how='left', suffixes=('', '_r'))")
        elif j["rel"] == "lookup":
            L.append(f"# {j['left']}를 호출하려면 {j['right']}의 {on['right']} 값이 필요 — 위 fetch의 params에 {on['left']}로 넣어 반복 호출")
        else:
            L.append(f"{lv} = {lv}.merge({rv}, left_on={on['left']!r}, right_on={on['right']!r}, how='left', suffixes=('', '_r'))")
        L.append("")
    return "\n".join(L).rstrip() + "\n"
