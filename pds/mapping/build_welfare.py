"""복지시설: 장기요양기관기호(ltc_instt_cd, 15059029 전수) ↔ 사회복지시설 코드(welfare_fclt_cd, 15001848 전수 중 노인 시설).

두 목록 모두 주소가 없다 — 시군구 코드(5자리)를 블록으로 이름만 비교한다.
  장기요양: siDoCd(2)+siGunGuCd(3)   사회복지시설: jrsdSggCd 앞 5자리
사회복지시설 이름의 2.8%는 마스킹(아동·정신·학대피해 쉼터 — 개인정보 보호)이라 매칭 대상에서 뺀다.
같은 운영자가 요양원·주야간보호·방문요양을 각각 등록하므로 이름이 같은 후보가 여럿이면 1:1이 아니라 미매칭으로 둔다.
"""
from __future__ import annotations

import re

import pandas as pd

from pds.mapping.common import match, norm_name, write
from pds.probe.fullpull import load

ELDER = r"노인|재가|요양"


def _nm(s) -> str:
    s = norm_name(s)
    return re.sub(r"(노인)?(요양원|요양센터|복지센터|주간보호센터|주야간보호센터|재가센터|재가복지센터|방문요양센터)$", "", s) or s


def build() -> dict:
    ltc = load("15059029", "ltc_instt")
    wf = load("15001848", "fclt_list")
    wf = wf[wf["fcltKindNm"].str.contains(ELDER, na=False) & ~wf["fcltNm"].str.contains(r"\*", na=False)]
    L = pd.DataFrame({"value": ltc["longTermAdminSym"].astype(str), "name": ltc["adminNm"], "nname": ltc["adminNm"].map(_nm),
                      "road": None, "sgg": ltc["siDoCd"].astype(str).str.zfill(2) + ltc["siGunGuCd"].astype(str).str.zfill(3)})
    R = pd.DataFrame({"value": wf["fcltCd"].astype(str) + ":" + wf["srvInstId"].astype(str), "name": wf["fcltNm"],
                      "nname": wf["fcltNm"].map(_nm), "road": None, "sgg": wf["jrsdSggCd"].astype(str).str[:5]}).drop_duplicates("value")
    m = match(L.drop_duplicates("value"), R, fuzzy_on="sgg", fuzzy_min=92)
    m["method"] = m["method"].replace({"name+sgg": "name+sgg5", "sgg+fuzzy": "sgg5+fuzzy"})
    return write("ltc_instt_cd__welfare_fclt_cd", {"key": "ltc_instt_cd", "system": "장기요양기관기호 (장기요양기관 검색 15059029 전수)"},
                 {"key": "welfare_fclt_cd", "system": "사회복지시설 fcltCd:srvInstId (사회복지시설정보서비스 15001848, 노인 시설)"},
                 "name_address_match", m, "keep_left", ["15059029", "15001848"],
                 f"장기요양 {len(L):,} · 노인 사회복지시설 {len(R):,}(마스킹 제외). 주소가 없어 시군구+이름만 — 신뢰도 낮음, "
                 "장기요양 재가기관(방문요양 등)은 사회복지시설 목록에 없는 경우가 많아 미매칭 다수가 정상")


if __name__ == "__main__":
    r = build()
    print({k: r[k] for k in ("rows", "match_rate", "notes")})
