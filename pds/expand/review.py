"""2차 확대 부문 검토 — 1차 판정(keep-core·keep-variant·review)을 부문별로 LLM이 초안 판정 (python -m pds.expand.review).

부문 검토 원칙 (_review_log.md · 1차 단계에서 사용자가 정한 것):
  · 무조건 유지: 그 분야의 핵심 — 개체 단위 원장(시설 하나·업소 하나·필지 하나·거래 하나), 등록·인허가 대장, 실시간·일별 데이터
  · 미룸: 통계·집계, 보조 자료, 수집 시점이 불규칙한 것, 기관 운영(홈페이지·민원·예산·채용·교육·홍보·연구보고서)
  · 통계 예외: 시군구·시도 × 월 격자로 지역에 이을 수 있거나 실제 원장에서 나온 집계는 유지
  · 잘못 분류된 것은 버리지 않고 제자리 부문으로 옮긴다
  · 이미 검증된 데이터와 겹치면(같은 원장의 다른 판) 표시
결과: knowledge/expansion/wave2/review/<부문>.yaml (데이터마다 판정·우선순위·세부 부문·역할·사유) + queue.parquet의 final_* 열
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from pds import config
from pds.expand.wave2 import OUT
from pds.schema import store

MODEL = "claude-sonnet-5-5"
BATCH = 40
TARGET = ("keep-core", "keep-variant", "review")
USAGE: list[tuple[int, int]] = []
ROLES = ["원장", "실시간", "시설목록", "코드·기준", "이력·변경", "통계·집계", "기타"]

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "decision", "priority", "subsector", "move_to", "role", "overlap_with", "reason"],
        "properties": {
            "id": {"type": "string"},
            "decision": {"type": "string", "enum": ["keep", "defer", "move"]},
            "priority": {"type": "integer", "enum": [1, 2, 3]},
            "subsector": {"type": "string", "description": "주어진 세부 부문 slug 중 하나, 맞는 게 없으면 'new:<짧은 이름>'"},
            "move_to": {"type": "string", "description": "decision=move일 때 옮길 부문 이름(예: '농축수산 - 농업'), 아니면 빈 문자열"},
            "role": {"type": "string", "enum": ROLES},
            "overlap_with": {"type": "string", "description": "겹치는 검증 데이터 id, 없으면 빈 문자열"},
            "reason": {"type": "string", "description": "한국어 한 줄 (60자 이내)"},
        }}}},
}

SYSTEM = """당신은 한국 공공데이터포털(data.go.kr) 데이터를 부문별로 검토하는 데이터 큐레이터입니다.
목표: 사용자 목표(상권 분석, 입지 비교, 시설 찾기 등)에 맞춰 여러 공공데이터를 조인해 쓰는 전략 시스템에 '2차로 편입할 데이터'를 고릅니다.
후보는 모두 조인 키(필지·좌표·법정동·사업자번호·기관코드·주소 등)를 가진 것으로 이미 걸러졌습니다.

판정 원칙
- keep (유지): 그 분야의 핵심 — 개체 단위 원장(시설·업소·필지·거래·차량·선박 하나가 한 행), 등록·인허가 대장, 실시간·일별 관측. 전국 범위면 더 좋다.
- defer (미룸): 통계·집계(기간·지역별 합계), 보조 자료, 수집 시점이 불규칙한 것, 기관 운영 자료(홈페이지·민원·예산·채용·교육·홍보·연구보고서), 한두 지역에만 의미 있는 소규모 목록.
  · 예외: 시군구·시도 × 월 격자처럼 지역에 이을 수 있는 집계, 실제 원장에서 나온 집계는 keep 가능.
- move (이동): 지금 부문이 틀린 데이터(예: 임업 영역에 있는 농업 데이터). 버리지 말고 move_to에 제자리 부문을 적는다. move도 편입 대상이다.
- priority: 1 = 바로 편입(전국 원장·실시간·다른 데이터와 많이 이어짐) · 2 = 편입 · 3 = 여유 있을 때.
- overlap_with: 이미 검증된 데이터와 같은 원장의 다른 판(지역판·영문판·구버전)이면 그 id. 이 경우 대개 defer.
- subsector: 아래 세부 부문 목록에서 고르고, 맞는 게 없으면 'new:<이름>'.
- reason: 한국어 한 줄, 판단 근거만 짧게.
모든 후보에 판정을 하나씩 돌려줍니다 (id를 빠뜨리지 않는다)."""


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else anthropic.Anthropic()


def _sector_context(sector_top: str) -> str:
    import yaml
    subs = yaml.safe_load((config.KNOWLEDGE / "sectors" / "subsectors.yaml").read_text(encoding="utf-8"))
    lines = ["세부 부문 (slug · 이름 · depth):"]
    for s in subs:
        if str(s.get("sector", "")).split(" - ")[0] != sector_top:
            continue
        lines.append(f"[{s['sector']}]")
        for x in s.get("subsectors") or []:
            lines.append(f"  {x['slug']} · {x['name']} · {x.get('depth', '')}")
    ver = [d for d in store.load("dataset") if str(d.get("sector", "")).split("/")[0] == sector_top and d.get("tier") == "verified"]
    lines.append(f"\n이 부문에서 이미 검증된 데이터 {len(ver)}개 (겹침 판단용):")
    lines += [f"  {d['id']} {d['title']}" for d in ver[:120]]
    return "\n".join(lines)


def _v(x, n: int | None = None) -> str:
    """결측(NaN·NA·None)은 '-' — 판다스 NA는 bool 평가가 안 된다."""
    if x is None or (not isinstance(x, (list, tuple)) and pd.isna(x)) or str(x).strip() == "":
        return "-"
    s = str(x).replace("\n", " ")
    return s[:n] if n else s


def _unit_line(r) -> str:
    desc = str(r.get("description") or "").replace("\n", " ")[:140]
    cols = str(r.get("output_cols") or "")[:160]
    fam = f" · 자치단체 {r['family_n']}곳" if r["local"] else ""
    return (f"- id={r['id']} | {r['title']} | {r['agency_name']} | {r['list_type']} | 부문 {r['sector']} / {_v(r.get('subsector_name'))}"
            f" | 키 {r['keys']} ({r['tier']}){fam} | 건수 {_v(r.get('row_count'))} · 갱신 {_v(r.get('update_cycle'))}"
            f" | 1차 {r['verdict']}: {r['reason']}\n    설명: {desc}\n    열: {cols}")


def _ask(sector_top: str, ctx: str, rows: pd.DataFrame) -> list[dict]:
    from pds.service.llm import FALLBACK, _text
    msg = f"부문: {sector_top}\n\n{ctx}\n\n후보 {len(rows)}개:\n" + "\n".join(_unit_line(r) for _, r in rows.iterrows())
    for attempt in range(3):
        try:
            r = _client().beta.messages.create(
                model=MODEL, max_tokens=12000, system=SYSTEM, **FALLBACK,
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": msg}])
            items = json.loads(_text(r))["items"]
            got = {x["id"] for x in items}
            missing = set(rows["id"]) - got
            if missing and attempt < 2:
                continue
            USAGE.append((r.usage.input_tokens, r.usage.output_tokens))
            return items
        except Exception as e:  # noqa: BLE001 — 다시 시도
            print(f"  ! {sector_top} 재시도 {attempt + 1}: {type(e).__name__}: {str(e)[:120]}")
    return []


def run(sectors: list[str] | None = None, workers: int = 6) -> pd.DataFrame:
    sys.stdout.reconfigure(encoding="utf-8")
    q = pd.read_parquet(OUT / "queue.parquet")
    cat = pd.read_parquet(config.PROCESSED / "catalog.parquet", columns=["id", "description", "output_cols"])
    q = q.merge(cat, on="id", how="left")
    todo = q[q["verdict"].isin(TARGET)]
    if sectors:
        todo = todo[todo["sector_top"].isin(sectors)]
    jobs = []
    for sec, g in todo.groupby("sector_top"):
        ctx = _sector_context(sec)
        g = g.sort_values(["sector", "verdict"])
        jobs += [(sec, ctx, g.iloc[i:i + BATCH]) for i in range(0, len(g), BATCH)]
    print(f"검토 {len(todo):,}개 · {len(jobs)}회 호출 · {MODEL}")
    out: dict[str, list] = {}
    with ThreadPoolExecutor(workers) as ex:
        for (sec, _, rows), res in zip(jobs, ex.map(lambda j: _ask(*j), jobs)):
            out.setdefault(sec, []).extend(res)
            print(f"  {sec} +{len(res)}/{len(rows)}")
    (OUT / "review").mkdir(parents=True, exist_ok=True)
    import yaml
    title = dict(zip(q["id"], q["title"]))
    for sec, items in out.items():
        doc = {"sector": sec, "reviewed_at": str(dt.date.today()), "reviewed_by": f"{MODEL} 초안 (원칙: pds/expand/review.py)",
               "items": [{"id": x["id"], "title": title.get(x["id"], ""), **{k: x[k] for k in ("decision", "priority", "subsector", "move_to",
                                                                                                "role", "overlap_with", "reason")}}
                         for x in sorted(items, key=lambda x: (x["decision"], x["priority"], x["id"]))]}
        (OUT / "review" / f"{sec}.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    res = pd.DataFrame([x for v in out.values() for x in v]).drop_duplicates("id")
    tin, tout = sum(u[0] for u in USAGE), sum(u[1] for u in USAGE)
    print(f"토큰 입력 {tin:,} · 출력 {tout:,} · 약 ${tin / 1e6 * 2 + tout / 1e6 * 10:.2f}")
    return res


def merge_final() -> pd.DataFrame:
    """부문 yaml(사람이 고친 것 포함)을 queue.parquet의 final_* 열로 합친다."""
    import yaml
    q = pd.read_parquet(OUT / "queue.parquet")
    rows = []
    for f in sorted((OUT / "review").glob("*.yaml")):
        rows += yaml.safe_load(f.read_text(encoding="utf-8"))["items"]
    r = pd.DataFrame(rows).add_prefix("final_").rename(columns={"final_id": "id"})
    q = q.drop(columns=[c for c in q.columns if c.startswith("final_")]).merge(r.drop(columns=["final_title"], errors="ignore"), on="id", how="left")
    auto = q["final_decision"].isna()
    q.loc[auto & q["verdict"].eq("absorb-std"), "final_decision"] = "absorb"
    q.loc[auto & q["verdict"].str.startswith("defer"), "final_decision"] = "defer"
    q.to_parquet(OUT / "queue.parquet", index=False)
    return q


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "merge":
        q = merge_final()
        print(q["final_decision"].value_counts(dropna=False).to_string())
    else:
        run(args or None)
        q = merge_final()
        print(q["final_decision"].value_counts(dropna=False).to_string())
