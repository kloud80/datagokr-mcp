"""코드 생성 — 전략 응답 → 그대로 돌아가는 Python (이 저장소 없이 requests·pandas만으로). LLM 없이 결정적으로 만든다.

호출은 검증 때 성공한 조건을 다시 꾸민 것(callspec.py): URL·필수 파라미터·형식·페이지 이름·실제 페이지 크기.
  · 응답 오류(resultCode·errMsg)는 빈 결과로 넘기지 않고 예외로 알린다. 게이트웨이 302·5xx는 잠깐 쉬고 다시 시도
  · 전체 건수(totalCount)까지 쪽을 넘긴다. MAX_ROWS로 상한 (전국 230만 건 같은 데이터가 있어서)
  · 목표 문장의 지역(성수동 → 성동구 11200)을 시군구·시도 파라미터에 넣는다
  · 다른 데이터의 값이 있어야 부를 수 있는 API(단지코드별 상세 등)는 그 데이터를 먼저 받아 값마다 호출
조인은 전략의 joins(선언된 Edge)만: 같은 키는 merge, 허브(PNU·법정동)는 각 데이터에 키 열을 만들어 키별로 모은다.
좌표·주소 → PNU는 브이월드 키(VWORLD_API_KEY)가 있어야 한다.
"""
from __future__ import annotations

import re

from pds.strategy.callspec import call_spec

PNU_HUB, BJD_HUB = "15123899", "15123287"
OK_FMT = re.compile(r"^(_type|type|datatype|resulttype|returntype|output)$", re.I)

HELPERS = r'''
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "datagokr-mcp-generated"


def _get(url, params, tries=4):
    """게이트웨이가 가끔 302(옛 주소로 돌림)·5xx를 준다 — 쉬었다 다시."""
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=60, allow_redirects=False)
            if r.status_code == 200:
                return r
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = repr(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url} 호출 실패 ({err}) — 포털 게이트웨이 상태나 활용신청 승인 여부를 확인하세요")


def _check(text):
    """HTTP 200이어도 오류일 수 있다 (키 미등록·필수 파라미터 누락·트래픽 초과)."""
    m = re.search(r'"?(resultCode|returnReasonCode)"?\s*[:>]\s*"?([^"<,}]+)', text)
    code = m.group(2).strip() if m else None
    msg = re.search(r'"?(resultMsg|returnAuthMsg|errMsg)"?\s*[:>]\s*"?([^"<]+)', text)
    msg = msg.group(2).strip() if msg else ""
    ok = code is None or re.fullmatch(r"(INFO-)?[A-Z]?0+|NORMAL_CODE|200", code) or re.search(r"NORMAL|정상|SUCCESS", msg, re.I)
    if not ok:
        raise RuntimeError(f"API 오류 {code}: {msg or text[:200]}")
    if "SERVICE_KEY_IS_NOT_REGISTERED" in text or "SERVICE ERROR" in text:
        raise RuntimeError("인증키 오류 — data.go.kr 마이페이지의 일반 인증키(Decoding)와 활용신청 승인 여부를 확인하세요")


def _rows_json(o):
    if isinstance(o, list):
        return o if o and isinstance(o[0], dict) else None
    if isinstance(o, dict):
        for k in ("item", "items", "data", "list", "row", "rows", "result", "body", "response"):
            if k in o:
                v = o[k]
                if k in ("item", "row") and isinstance(v, dict) and v and all(not isinstance(x, (dict, list)) for x in v.values()):
                    return [v]
                got = _rows_json(v)
                if got is not None:
                    return got
        for v in o.values():
            if isinstance(v, (dict, list)):
                got = _rows_json(v)
                if got:
                    return got
    return None


def _total(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k.lower() in ("totalcount", "total_count", "totalcnt", "matchcount") and str(v).isdigit():
                return int(v)
            t = _total(v)
            if t is not None:
                return t
    return None


def _parse(r):
    text = r.text
    _check(text)
    if text.lstrip().startswith(("{", "[")):
        o = r.json()
        return _rows_json(o) or [], _total(o)
    root = ET.fromstring(r.content)
    items = root.findall(".//item") or root.findall(".//row")
    m = root.find(".//totalCount")
    return [{c.tag: (c.text or "").strip() for c in it} for it in items], int(m.text) if m is not None and (m.text or "").isdigit() else None


def fetch(url, params=None, page="pageNo", size="numOfRows", page_size=100, max_rows=None, key_param="serviceKey", key=None):
    """data.go.kr API를 끝 쪽까지(또는 max_rows까지) 받아 DataFrame으로."""
    max_rows = MAX_ROWS if max_rows is None else max_rows
    rows, n, total = [], 1, None
    while True:
        q = {**(params or {}), key_param: key or SERVICE_KEY}
        if page:
            q[page], q[size] = n, page_size
        got, t = _parse(_get(url, q))
        total = total if total is not None else t
        rows += got
        if not page or not got or len(got) < page_size or (total and len(rows) >= total) or (max_rows and len(rows) >= max_rows):
            break
        n += 1
        if n % 20 == 0:
            print(f"  … {url.rsplit('/', 1)[-1]} {len(rows):,}/{total or '?'}")
    rows = rows[:max_rows] if max_rows else rows
    if total and max_rows and total > len(rows):
        print(f"  ! {url.rsplit('/', 1)[-1]}: 전체 {total:,}건 중 {len(rows):,}건만 받음 (MAX_ROWS) — 전부 받으려면 MAX_ROWS = None")
    return pd.DataFrame(rows)


def fetch_each(url, params, key_name, values, **kw):
    """다른 데이터의 값(단지코드 등)마다 호출해 이어 붙인다."""
    out = []
    for v in list(dict.fromkeys(values))[: (MAX_ROWS or 10**9)]:
        try:
            out.append(fetch(url, {**params, key_name: v}, **kw).assign(**{key_name: v}))
        except RuntimeError as e:
            print(f"  ! {key_name}={v}: {e}")
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


MAPPING_DIR = os.environ.get("PDS_MAPPING_DIR", "knowledge/mappings")
MAPPING_URL = "https://raw.githubusercontent.com/kloud80/datagokr-mcp/main/knowledge/mappings/"


def load_mapping(name):
    """키 매핑표(실측으로 만든 대응표) — 이 저장소의 knowledge/mappings, 없으면 GitHub에서."""
    for src in (os.path.join(MAPPING_DIR, name + ".parquet"), MAPPING_URL + name + ".parquet"):
        try:
            return pd.read_parquet(src)
        except Exception:  # noqa: BLE001 — 다음 위치로
            continue
    print(f"  ! 매핑표 {name} 를 찾지 못해 이 조인은 건너뜀 — PDS_MAPPING_DIR 로 경로를 알려 주세요")
    return None


def read_file(path, url):
    """포털에서 내려받은 파일. 아직 없으면 안내만 하고 건너뛴다."""
    if not os.path.exists(path):
        print(f"  ! {path} 없음 — {url} 에서 내려받아 이 이름으로 저장하세요 (이번 실행에서는 건너뜀)")
        return None
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path}: 인코딩을 알 수 없음")
'''

VWORLD = r'''

# ── 좌표·주소 → 필지고유번호(PNU): 브이월드 (https://www.vworld.kr 에서 인증키 발급, 무료)
VWORLD_KEY = os.environ.get("VWORLD_API_KEY")
VWORLD_DOMAIN = os.environ.get("VWORLD_DOMAIN", "")


@lru_cache(maxsize=None)
def coord_to_pnu(lat, lon):
    """그 점을 포함하는 필지의 PNU (연속지적도 LP_PA_CBND_BUBUN)."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    r = SESSION.get("https://api.vworld.kr/req/data", timeout=30, params={
        "service": "data", "request": "GetFeature", "data": "LP_PA_CBND_BUBUN", "geomFilter": f"POINT({lon} {lat})",
        "format": "json", "size": 1, "geometry": "false", "key": VWORLD_KEY, "domain": VWORLD_DOMAIN})
    feats = (((r.json().get("response") or {}).get("result") or {}).get("featureCollection") or {}).get("features") or []
    return feats[0]["properties"].get("pnu") if feats else None


@lru_cache(maxsize=None)
def address_to_coord(address):
    """주소 → (위도, 경도). 도로명 먼저, 안 되면 지번."""
    if not isinstance(address, str) or not address.strip():
        return None
    for typ in ("road", "parcel"):
        r = SESSION.get("https://api.vworld.kr/req/address", timeout=30, params={
            "service": "address", "request": "getcoord", "crs": "epsg:4326", "address": address,
            "format": "json", "type": typ, "key": VWORLD_KEY})
        res = r.json().get("response") or {}
        if res.get("status") == "OK":
            pt = res["result"]["point"]
            return float(pt["y"]), float(pt["x"])
    return None


def address_to_pnu(address):
    c = address_to_coord(address)
    return coord_to_pnu(*c) if c else None
'''


def _var(i: str) -> str:
    return "df_" + re.sub(r"\W", "_", i)


def _short(t: str) -> str:
    return t.split("_", 1)[1] if "_" in t else t


def _region_codes(p: dict) -> dict:
    """목표 지역 → {'sgg5': '11200', 'sido2': '11', 'name': '서울특별시 성동구'} (법정동 코드표)."""
    names = (p.get("region") or {}).get("names") or []
    if not names:
        return {}
    import pandas as pd
    from pds import config
    t = pd.read_parquet(config.KNOWLEDGE / "codes" / "bjd_cd.parquet")
    t = t[t["valid"]]
    for n in reversed(names):  # 가장 좁은 지명부터
        hit = t[t["name"].str.split().str[-1].str.replace(r"\d*가$", "", regex=True).eq(re.sub(r"\d*가$", "", n))
                | t["name"].str.endswith(n)]
        if len(hit):
            code = str(hit.iloc[0]["code"])
            sgg = t[t["code"].astype(str).eq(code[:5] + "00000")]
            name = sgg.iloc[0]["name"] if len(sgg) else hit.iloc[0]["name"]
            return {"sgg5": code[:5], "sido2": code[:2], "bjd10": code if code[5:] != "00000" else None,
                    "name": name, "goal_name": n, "instt": _instt_code(name)}
    return {}


def _instt_code(name: str) -> str | None:
    """'서울특별시 성동구' → 행정표준 기관코드 3030000 (인허가 API의 개방자치단체코드와 같은 체계)."""
    import pandas as pd
    from pds import config
    t = pd.read_parquet(config.KNOWLEDGE / "codes" / "instt_cd.parquet", columns=["code", "name"])
    hit = t[t["name"].eq(name)]
    return str(hit.iloc[0]["code"]) if len(hit) else None


def _localize(params: dict, reg: dict, region_params: dict | None = None) -> tuple[dict, list[str]]:
    """표본 지역값(종로구 11110 등)을 목표 지역으로. 자릿수가 같은 것만 바꾼다."""
    out, notes = dict(params), []
    if not reg:
        return out, notes
    for k, v in params.items():
        s = str(v)
        if re.search(r"(lawd_cd|sigungu|signgu|sgg)", k, re.I) and re.fullmatch(r"\d{5}", s):
            out[k] = reg["sgg5"]
            notes.append(f"{k}={reg['sgg5']} ({reg['name']})")
        elif re.search(r"(sido|ctprvn|areacode|brtc)", k, re.I) and re.fullmatch(r"\d{2}", s):
            out[k] = reg["sido2"]
            notes.append(f"{k}={reg['sido2']}")
    rp = region_params or {}  # 선택 파라미터로 지역 거르기 — 전국을 받지 않게
    if not notes:
        if rp.get("instt") and reg.get("instt"):
            out[rp["instt"]] = reg["instt"]
            notes.append(f"{rp['instt']}={reg['instt']} ({reg['name']} 개방자치단체코드)")
        elif rp.get("sgg5"):
            out[rp["sgg5"]] = reg["sgg5"]
            notes.append(f"{rp['sgg5']}={reg['sgg5']} ({reg['name']})")
        elif rp.get("addr_like"):
            out[rp["addr_like"]] = reg["name"].split()[-1]
            notes.append(f"{rp['addr_like']}={reg['name'].split()[-1]}")
    return out, notes


def render(p: dict) -> str:
    ds = {d["id"]: d for d in p["datasets"]}
    reg = _region_codes(p)
    need: dict[str, set] = {}
    for j in p["joins"]:
        need.setdefault(j["left"], set()).update(j["on"].get("left") or [])
        need.setdefault(j["right"], set()).update(j["on"].get("right") or [])
    specs = {i: call_spec(i, tuple(sorted(need.get(i, ())))) for i in ds}
    joins = p["joins"]
    need_vworld = any(j.get("on", {}).get("transform") in ("R-12", "R-13") for j in joins)

    # 값 공급 관계: X의 필수 파라미터(kaptCode 등)를 Y의 열이 채운다 → Y를 먼저 받는다
    feeds: dict[str, tuple[str, str, str]] = {}
    for j in joins:
        for a, b, ca, cb in ((j["left"], j["right"], (j["on"].get("left") or [None])[0], (j["on"].get("right") or [None])[0]),
                             (j["right"], j["left"], (j["on"].get("right") or [None])[0], (j["on"].get("left") or [None])[0])):
            s = specs.get(a)
            if s and ca and ca in s["params"] and b in ds and a not in feeds:
                feeds[a] = (b, ca, cb)
    order = [i for i in ds if i not in feeds] + [i for i in ds if i in feeds]

    portal = [i for i in ds if specs.get(i)]
    L = ['"""' + f"자동 생성 — 목표: {p['goal']}",
         f"지식 버전 {p.get('knowledge_version')} · 호출 조건은 검증 때 성공한 것 · 조인은 선언된 Edge만",
         "",
         "준비: pip install requests pandas",
         "      data.go.kr 에서 아래 API 활용신청(대부분 자동승인) → 마이페이지 '일반 인증키(Decoding)'를 환경변수로",
         "      export DATA_GO_KR_SERVICE_KEY='...'" + ("    # 좌표·주소 → 필지 변환에는 VWORLD_API_KEY도" if need_vworld else ""),
         '"""',
         "import os", "import re", "import time", "import xml.etree.ElementTree as ET"]
    if need_vworld:
        L.append("from functools import lru_cache")
    L += ["", "import pandas as pd", "import requests", "",
          "SERVICE_KEY = os.environ['DATA_GO_KR_SERVICE_KEY']",
          "MAX_ROWS = 2000  # 데이터마다 최대 행 수 — 전부 받으려면 None (전국 수백만 건은 수 시간 걸린다)"]
    if reg:
        L.append(f"REGION = {reg['name']!r}  # 목표 문장의 '{reg['goal_name']}' — 시군구 코드 {reg['sgg5']}")
    L.append(HELPERS.rstrip())
    if need_vworld:
        L.append(VWORLD.rstrip())
    L += ["", "", "# ── 데이터 받기"]

    for i in order:
        d = ds[i]
        s = specs.get(i)
        v = _var(i)
        L.append("")
        title = f"# [{d['role']}] {i} {d['title']}"
        if s:
            info = []
            if s.get("total_count"):
                info.append(f"전체 {s['total_count']:,}건")
            info.append(f"쪽당 {s['page_size']}건" if s["page"] else "쪽 없음")
            info.append(f"검증 {s['verified_at']} · {s['fmt']}")
            L.append(title + " — " + " · ".join(info))
            params, notes = _localize(s["params"], reg, s.get("region_params"))
            if notes:
                L.append("#   지역을 목표에 맞춤: " + ", ".join(notes))
            elif reg:
                L.append(f"#   이 API는 지역 조건이 없어 전국을 받는다 — {reg['name']}만 쓰려면 MAX_ROWS = None 으로 전부 받은 뒤 주소 열로 거른다")
            other = [k for k in s["user_params"] if k not in {n.split("=")[0] for n in notes} and not (i in feeds and feeds[i][1] == k)]
            if other:
                L.append("#   목적에 맞게 바꿀 값: " + ", ".join(f"{k}={params[k]!r}" for k in other))
            kw = f"page={s['page']!r}, size={s['size']!r}, page_size={s['page_size']}" if s["page"] else "page=None"
            if i in feeds:
                src, pname, scol = feeds[i]
                params.pop(pname, None)
                L.append(f"#   {pname}는 {_short(ds[src]['title'])}({src})의 {scol} 값마다 호출 — 호출 수가 많으면 MAX_ROWS로 조절")
                L.append(f"{v} = fetch_each({s['url']!r}, {params!r}, {pname!r}, {_var(src)}[{scol!r}].dropna(), {kw})")
            else:
                L.append(f"{v} = fetch({s['url']!r}, {params!r}, {kw})")
        elif (d.get("access") or {}).get("channel") == "external":
            iss = (d.get("access") or {}).get("issuer") or "외부 사이트"
            L.append(title)
            L.append(f"#   {iss} 인증키로 부르는 외부 API — 포털 키로는 안 된다. 발급·호출 방법: {d.get('portal_url')}")
            L.append(f"{v} = None  # TODO: {iss} 키로 받아 DataFrame으로")
        else:
            L.append(title)
            L.append(f"#   파일 데이터 — 포털에서 내려받아 경로를 넣는다: {d.get('portal_url')}")
            L.append(f"{v} = read_file({(i + '.csv')!r}, {d.get('portal_url')!r})")
        L.append(f"print({i!r}, len({v}) if {v} is not None else '받지 않음')")

    # ── 조인
    hub_cols: dict[str, list[str]] = {"pnu": [], "bjd_cd": []}
    merged_lines = []
    for j in joins:
        on, t = j["on"], j["on"].get("transform")
        a, b = j["left"], j["right"]
        hub = b if b in (PNU_HUB, BJD_HUB) else a if a in (PNU_HUB, BJD_HUB) else None
        if j.get("rel") == "lookup" or (a in feeds and feeds[a][0] == b) or (b in feeds and feeds[b][0] == a):
            continue  # 값 공급으로 이미 이어 받음
        rate = f"실측 {j['match_rate']:.0%}" if j.get("match_rate") is not None else "미측정 — 결과를 눈으로 확인"
        if hub:
            x = a if hub == b else b
            if x not in ds:
                continue
            cols = on.get("left") if hub == b else on.get("right")
            v = _var(x)
            key = "pnu" if hub == PNU_HUB else "bjd_cd"
            line = f"# {j['edge']}: {_short(ds[x]['title'])} → {'필지(PNU)' if key == 'pnu' else '법정동'} · {rate}"
            cols = list(cols or [])
            if not cols:
                continue
            if t == "R-12" and len(cols) < 2:
                code = f"# 좌표 열 {cols[0]} 하나 — 위도·경도로 나눈 뒤 coord_to_pnu(위도, 경도)로 PNU를 붙인다"
            elif t == "R-12":
                code =f"{v}['pnu'] = [coord_to_pnu(a, b) for a, b in zip({v}[{cols[0]!r}], {v}[{cols[1]!r}])]"
            elif t == "R-13":
                code = f"{v}['pnu'] = {v}[{cols[0]!r}].map(address_to_pnu)  # 주소 → 좌표 → PNU (행마다 브이월드 2회 호출)"
            elif t == "R-02":
                code = f"{v}['bjd_cd'] = {v}[{cols[0]!r}].astype(str).str[:10]  # 시군구 단위면 앞 5자리"
            elif t == "R-14":
                code = (f"# 행정구역 이름({cols[0]}) → 코드: 법정동 코드표(https://www.code.go.kr)에서 이름으로 찾아 {v}['bjd_cd']를 채운다")
            else:
                code = f"{v}[{key!r}] = {v}[{cols[0]!r}].astype(str)"
            cond = f"if {v} is not None and len({v}) and all(c in {v} for c in {list(cols)!r}):"
            merged_lines += [line, cond, f"    {code}" if not code.startswith("#") else f"    pass  {code}",
                             f"elif {v} is not None and len({v}):", f"    print({'  ! ' + x + ': 조인 열 ' + ', '.join(cols) + ' 이 응답에 없어 건너뜀'!r})"]
            hub_cols[key].append(x)
        elif j.get("via_mapping"):
            la, rb = _var(a), _var(b)
            merged_lines += [f"# {j['edge']}: {_short(ds[a]['title'])} ⋈ {_short(ds[b]['title'])} · 매핑표 {j['via_mapping']} · {rate}",
                             f"m = load_mapping({j['via_mapping']!r})  # left_value → right_value",
                             f"if m is not None and {la} is not None and {rb} is not None and len({la}) and len({rb}):",
                             f"    {la} = {la}.merge(m[['left_value', 'right_value']], left_on={on['left'][0]!r}, right_on='left_value', how='left')",
                             f"    {la} = {la}.merge({rb}, left_on='right_value', right_on={on['right'][0]!r}, how='left', suffixes=('', '_{b}'))"]
        elif a in ds and b in ds:
            la, rb = _var(a), _var(b)
            merged_lines += [f"# {j['edge']}: {_short(ds[a]['title'])} ⋈ {_short(ds[b]['title'])} · {on.get('left')} = {on.get('right')} · {rate}",
                             f"if {la} is not None and {rb} is not None and len({la}) and len({rb}):",
                             f"    {la} = {la}.merge({rb}, left_on={on['left']!r}, right_on={on['right']!r}, how='left', suffixes=('', '_{b}'))"]
    if merged_lines:
        L += ["", "", "# ── 잇기 (선언된 조인만)"] + merged_lines
    for key, xs in hub_cols.items():
        if len(xs) >= 1:
            name = "by_pnu" if key == "pnu" else "by_bjd"
            label = "필지(PNU)" if key == "pnu" else "법정동"
            L += ["", f"# {label}별로 모은다 — 데이터마다 한 {label}에 여러 행일 수 있어 옆으로 merge하지 않고 세로로 쌓는다",
                  f"{name} = pd.concat([d.assign(_source=s) for s, d in {{" + ", ".join(f"{x!r}: {_var(x)}" for x in xs) + "}.items()",
                  f"                    if d is not None and {key!r} in d], ignore_index=True)",
                  f"print({name}.groupby([{key!r}, '_source']).size().unstack(fill_value=0).head(20))  # {label}마다 데이터별 건수"]
    return "\n".join(L).rstrip() + "\n"
