"""교통 노드: TAGO 정류소 노드ID(tago_node_id, 15098534 도시별 전수) ↔ 국토부 표준 버스정류장 ID(busstop_sttn_id, 15142032 시군구별 전수).

공통 코드가 없다(실측: 숫자부 겹침 12%는 우연). 국토부 원장은 좌표가 없고 ARS 번호도 대부분 '~'.
1) TAGO 도시코드 → 시군구: 이름이 정확히 같은 정류장 쌍의 시군구 투표 (옛 행정구역 코드 체계라 직접 대응 불가)
2) 그 시군구 안에서 정류장 이름이 양쪽 모두 유일할 때만 1:1 — 길 양쪽 같은 이름 쌍은 방향을 구분할 수 없어 미매칭
서울은 TAGO에 없다 (서울시 정류소정보 API 별도).
"""
from __future__ import annotations

import pandas as pd

from pds.mapping.common import norm_name, write
from pds.probe.fullpull import load


def build() -> dict:
    t = load("15098534", "sttn_no_list")
    b = load("15142032", "bus_stop")
    t["n"] = t["nodenm"].map(norm_name)
    b["n"] = b["sttn_nm"].map(norm_name)
    t["city"] = t["_q_cityCode"].astype(str)
    b["sgg"] = b["sgg_cd"].astype(str)
    # 1) 도시코드 → 시군구 투표 (이름이 전국에서 흔하지 않은 것만)
    common = b["n"].value_counts()
    rare = set(common[common <= 3].index)
    v = t[t.n.isin(rare)].merge(b[b.n.isin(rare)][["n", "sgg"]], on="n")
    vote = v.groupby(["city", "sgg"]).size().reset_index(name="votes")
    tot = v.groupby("city").size()
    vote["share"] = vote["votes"] / vote["city"].map(tot)
    city_sgg = vote[vote["share"] >= 0.05].groupby("city")["sgg"].apply(set).to_dict()  # 통합시·광역시는 여러 구
    # 2) 시군구 안 유일 이름
    rows = []
    b_cnt = b.groupby(["sgg", "n"]).size()
    for city, g in t.groupby("city"):
        sggs = city_sgg.get(city)
        if not sggs:
            continue
        bb = b[b.sgg.isin(sggs)]
        bu = bb[bb.groupby("n")["n"].transform("size") == 1]
        tu = g[g.groupby("n")["n"].transform("size") == 1]
        m = tu.merge(bu[["n", "sttn_id"]], on="n")
        rows.append(pd.DataFrame({"left_value": m["nodeid"], "right_value": m["sttn_id"].astype(str), "confidence": 0.8,
                                  "method": "city→sgg vote + unique name"}))
        # 같은 이름 2~3개 묶음이 양쪽에 같은 수로 있으면 묶음끼리 교차 대응 (방향 미구분, 장소 단위 조인용)
        gc, bc = g.groupby("n").size(), bb.groupby("n").size()
        grp = [n for n in gc.index.intersection(bc.index) if 2 <= gc[n] <= 3 and gc[n] == bc[n]]
        if grp:
            x = g[g.n.isin(grp)][["n", "nodeid"]].merge(bb[bb.n.isin(grp)][["n", "sttn_id"]], on="n")
            rows.append(pd.DataFrame({"left_value": x["nodeid"], "right_value": x["sttn_id"].astype(str), "confidence": 0.5,
                                      "method": "name group (방향 미구분)"}))
    got = pd.concat(rows, ignore_index=True)
    uniq = got[got.method.str.startswith("city")].drop_duplicates("right_value", keep=False)
    grp = got[got.method.str.startswith("name group")]
    grp = grp[~grp.right_value.isin(uniq.right_value) & ~grp.left_value.isin(uniq.left_value)]
    got = pd.concat([uniq, grp], ignore_index=True)
    miss = t.loc[~t.nodeid.isin(got.left_value), "nodeid"].drop_duplicates()
    m = pd.concat([got, pd.DataFrame({"left_value": miss, "right_value": None, "confidence": 0.0, "method": "unmatched"})],
                  ignore_index=True)
    return write("tago_node_id__busstop_sttn_id", {"key": "tago_node_id", "system": "TAGO 정류소 nodeid (15098534, 도시코드별 전수, 서울 제외)"},
                 {"key": "busstop_sttn_id", "system": "국토부 표준 버스정류장 sttn_id (15142032, 시군구별 전수)"},
                 "name_address_match", m, "keep_left", ["15098534", "15142032"],
                 f"TAGO {t.nodeid.nunique():,} · 국토부 {b.sttn_id.nunique():,}. 도시코드→시군구 대응 {len(city_sgg)}/{t.city.nunique()} 도시. "
                 "좌표·공통코드가 없어 ①이름 유일 1:1(0.8) ②같은 이름 2~3개 묶음 교차(0.5, 방향 미구분 — 한 left에 right 여러 행) — "
                 "정류장 단위 조인은 ①만, 장소 단위 집계는 ②까지")


if __name__ == "__main__":
    r = build()
    print({k: r[k] for k in ("rows", "match_rate", "notes")})
