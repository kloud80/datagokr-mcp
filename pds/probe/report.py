"""Phase 2 라운드 실행·요약 — 대상마다 run_one을 돌리고, runs/stats/apply/specs를 모아 사람이 읽는 표로 만든다.

실행: python -m pds probe-run [round] → probe/runs, probe/stats, probe/data
요약: python -m pds probe-report [round] → reports/phase2_round{n}.md
"""
from __future__ import annotations

import json
from pathlib import Path

from pds import config

P = config.ROOT / "probe"


def _load(sub: str, dsid: str) -> dict | None:
    f = P / sub / f"{dsid}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def targets(rnd: str) -> list[dict]:
    return [t for t in json.loads((config.KNOWLEDGE / "targets.json").read_text(encoding="utf-8")) if t["round"] == rnd]


def run_round(rnd: str = "1", max_rows: int = 1000, skip_done: bool = True) -> list[dict]:
    from pds.probe.deep import run_one
    out = []
    for t in targets(rnd):
        if t["kind"] not in ("REST", "SOAP"):
            continue
        prev = _load("runs", t["id"])
        if skip_done and prev and prev.get("ok_ops"):
            out.append(prev)
            continue
        try:
            out.append(run_one(t["id"], max_rows=max_rows))
        except Exception as e:  # noqa: BLE001
            out.append({"id": t["id"], "error": repr(e)[:300]})
    return out


def _verdict(run: dict | None, apply: dict | None) -> str:
    if not run:
        return "미실행"
    if run.get("skipped"):
        return "명세없음"
    if run.get("ok_ops"):
        return "성공"
    errs = " ".join(str(a.get("error") or a.get("body_head") or "") for o in run.get("ops", []) for a in o.get("attempts", []))
    if "unauthorized" in errs or "NOT_REGISTERED" in errs:
        return "키미등록" if not apply or apply.get("result") != "submitted" else "승인대기"
    if any(o.get("needs_params") for o in run.get("ops", [])):
        return "파라미터부족"
    return "응답0행"


def build_report(rnd: str = "1") -> str:
    rows, lines = [], []
    for t in targets(rnd):
        run, stats, apply, spec = (_load(s, t["id"]) for s in ("runs", "stats", "apply", "specs"))
        v = _verdict(run, apply) if t["kind"] in ("REST", "SOAP") else "파일(별도)"
        ok_ops = [o for o in (run or {}).get("ops", []) if o.get("ok")]
        cols = sorted({c for o in ok_ops for c in o.get("columns", [])})
        ms = [a["ms"] for o in (run or {}).get("ops", []) for a in o.get("attempts", []) if "ms" in a]
        rows.append({"id": t["id"], "title": t["title"], "sector": t["sector"], "subsector": t["subsector"], "verdict": v,
                     "review": (apply or {}).get("심의여부"), "ops": f"{len(ok_ops)}/{len((run or {}).get('ops', []))}",
                     "rows": sum(o.get("rows", 0) for o in ok_ops), "total": max([o.get("total_count") or 0 for o in ok_ops] or [0]),
                     "ms": int(sum(ms) / len(ms)) if ms else None, "ncols": len(cols), "cols": cols[:15],
                     "swagger": (spec or {}).get("swagger")})
    from collections import Counter
    cnt = Counter(r["verdict"] for r in rows)
    lines += [f"# Phase 2 라운드 {rnd} — 호출·다운로드·셀 통계 결과", "",
              f"대상 {len(rows)}건 · " + " · ".join(f"{k} {v}" for k, v in cnt.most_common()), "",
              "| 판정 | 데이터 | 부문/세부 | 심의 | 성공 오퍼레이션 | 받은 행 | 전체 건수 | 평균 ms | 컬럼 수 | 대표 컬럼 |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    order = {"성공": 0, "응답0행": 1, "파라미터부족": 2, "승인대기": 3, "키미등록": 4, "명세없음": 5, "미실행": 6, "파일(별도)": 7}
    for r in sorted(rows, key=lambda r: (order.get(r["verdict"], 9), r["sector"])):
        lines.append(f"| {r['verdict']} | [{r['title']}](https://www.data.go.kr/data/{r['id']}/openapi.do) | {r['sector']}<br>{r['subsector']} | "
                     f"{r['review'] or ''} | {r['ops']} | {r['rows']:,} | {r['total']:,} | {r['ms'] or ''} | {r['ncols']} | "
                     f"{', '.join(r['cols'][:8])} |")
    path = config.REPORTS / f"phase2_round{rnd}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (P / f"summary_round{rnd}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(path)
