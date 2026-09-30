"""의료기관: 심평원 요양기관(ykiho, 15001698 병원정보 전수) ↔ 국립중앙의료원 기관ID(hpid, 15000736 병·의원 전수).

같은 병원을 두 기관이 다른 코드로 가진다(consolidate §9-6). 이름+도로명주소 → 이름+시군구 → 도로명 안 유사도 → 좌표 50m.
hpid 쪽에는 구급차·약국 등 요양기관이 아닌 기관도 섞여 있어 오른쪽 미매칭은 정상.
"""
from __future__ import annotations

from pds.mapping.common import match, prepare, write
from pds.probe.fullpull import load


def build() -> dict:
    a = load("15001698", "hosp_basis")
    b = load("15000736", "hsptl_mdcnc")
    L = prepare(a, "ykiho", "yadmNm", ["addr"], lat="YPos", lon="XPos")
    R = prepare(b, "hpid", "dutyName", ["dutyAddr"], lat="wgs84Lat", lon="wgs84Lon")
    m = match(L, R, use_coord=True)
    m = m.merge(a[["ykiho", "clCdNm"]].rename(columns={"ykiho": "left_value", "clCdNm": "left_kind"}), on="left_value", how="left")
    by_kind = m.assign(ok=m.right_value.notna()).groupby("left_kind")["ok"].mean().sort_values()
    return write("ykiho__hpid", {"key": "ykiho", "system": "심평원 요양기관 ykiho (병원정보서비스 15001698 전수)"},
                 {"key": "hpid", "system": "국립중앙의료원 hpid (전국 병·의원 찾기 15000736 전수)"},
                 "composite", m, "keep_left", ["15001698", "15000736"],
                 f"요양기관 {len(L):,} · NMC 기관 {len(R):,}. 종별 매칭률 낮은 순: "
                 + ", ".join(f"{k} {v:.0%}" for k, v in by_kind.head(4).items()))


if __name__ == "__main__":
    r = build()
    print({k: r[k] for k in ("rows", "match_rate", "notes")})
