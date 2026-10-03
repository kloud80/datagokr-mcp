"""파라미터 수리 재시도 — 검증 실패한 포털 API를 명세·오류 응답을 보고 다시 부른다 (python -m pds.probe.repair [id ...]).

실패 대부분은 키가 아니라 파라미터 문제다: 필수값 누락(NO_MANDATORY_REQUEST_PARAMETERS), 값 형식 오류(INVALID_REQUEST_PARAMETER),
예시 기간에 자료가 없음(NODATA). LLM(PDS_REPAIR_MODEL, 기본 Sonnet)이 오퍼레이션 명세(요청 변수 설명·응답 필드 설명의 코드표)와
마지막 오류 응답을 읽고 파라미터 값을 제안하면, 실제로 불러 행이 나온 것만 knowledge/probe_params.yaml에 남긴다
(값을 지어낸 것인지는 호출 결과가 판정한다 — 0건이면 버린다). 이후 deep.run_one으로 정식 실측 기록을 다시 만든다.
"""
from __future__ import annotations

import json
import os
import re
import sys

import httpx

from pds import config
from pds.probe import deep

MODEL = os.environ.get("PDS_REPAIR_MODEL") or "claude-opus-5-5"
ROUNDS = 3
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["params", "why"],
          "properties": {"params": {"type": "array", "description": "덮어쓸 파라미터. drop=true면 보내지 않음",
                                    "items": {"type": "object", "additionalProperties": False, "required": ["name", "value", "drop"],
                                              "properties": {"name": {"type": "string"}, "value": {"type": "string"},
                                                             "drop": {"type": "boolean"}}}},
                         "why": {"type": "string", "description": "한국어 한 줄 근거"}}}
SYSTEM = """너는 공공데이터포털 OpenAPI 호출을 고치는 엔지니어다. 오퍼레이션 명세와 지금까지의 시도·응답을 보고,
행이 나오도록 덮어쓸 쿼리 파라미터를 JSON으로 제안한다.
- serviceKey·pageNo·numOfRows는 건드리지 않는다. 응답 형식 파라미터(type·_type·resultType·dataType)는 json으로.
- 필수 파라미터가 비면 명세 설명·응답 필드 설명에 나온 코드값이나 전국 대표값(서울 11·서울 종로구 11110·법정동 1111010100,
  최근 날짜, 대표 기관)을 넣는다. 날짜는 오늘 기준 최근 1~3개월 안으로.
- 결과를 지나치게 좁히는 선택 필터(이름·주소·번호)는 null로 뺀다.
- NODATA면 기간을 넓히거나 다른 대표값으로 바꾼다. 같은 시도를 반복하지 않는다."""


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else anthropic.Anthropic()


def _op_text(op: dict) -> str:
    ps = [f"- {p['name']} ({'필수' if p.get('required') else '선택'}, {p.get('type')}) {p.get('desc') or ''}"
          + (f" 예시={p['example']}" if p.get("example") not in (None, "") else "") for p in op.get("params") or []]
    rf = [f"- {f['name'].split('.')[-1]}: {f.get('desc') or ''}"[:160] for f in op.get("response_fields") or []][:40]
    return f"오퍼레이션 {op['path']} — {op.get('summary') or ''}\n요청 변수:\n" + "\n".join(ps) + "\n응답 필드(코드 설명 참고):\n" + "\n".join(rf)


def _ask(op: dict, history: list[dict], today: str) -> dict | None:
    from pds.service.llm import _text
    hist = "\n".join(f"시도 {k + 1}: params={json.dumps(h['params'], ensure_ascii=False)} → {h['result']}" for k, h in enumerate(history))
    msg = f"오늘 {today}\n\n{_op_text(op)}\n\n지금까지:\n{hist}\n\n다음에 시도할 파라미터를 제안하라."
    try:
        r = _client().messages.create(model=MODEL, max_tokens=1500, system=SYSTEM, messages=[{"role": "user", "content": msg}],
                                      output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}})
        out = json.loads(_text(r))
        out["params"] = {x["name"]: (None if x["drop"] else x["value"]) for x in out["params"]}
        return out
    except Exception as e:  # noqa: BLE001
        print(f"   ! LLM 실패 {type(e).__name__}: {str(e)[:100]}")
        return None


def _result(rec: dict) -> str:
    a = (rec.get("attempts") or [{}])[-1]
    return f"status={a.get('status')} rows={rec.get('rows')} " + (a.get("error") or (a.get("body_head") or "")[:220].replace("\n", " "))


def repair_one(dsid: str) -> dict | None:
    """성공하면 {op path: params} — probe_params.yaml에 넣을 값."""
    sp = config.ROOT / "probe" / "specs" / f"{dsid}.json"
    if not sp.exists():
        return None
    spec = json.loads(sp.read_text(encoding="utf-8"))
    if not spec.get("swagger") or not spec.get("operations"):
        return None
    scheme = "https" if "https" in (spec.get("schemes") or ["https"]) else "http"
    base = f"{scheme}://{spec['host']}{spec.get('base_path') or ''}"
    key = deep.service_key()
    import datetime as dt
    today = dt.date.today().isoformat()
    fixed, any_ok = {}, False
    with httpx.Client(headers={"User-Agent": "pds-probe/0.1"}) as client:
        for op in [o for o in spec["operations"] if o.get("method", "GET") == "GET"][:3]:
            extra = deep.overrides(dsid, op["path"])
            rec = deep.call_op(client, base, op, key, 100, extra=extra)
            if rec["ok"]:
                any_ok = True
                continue
            hist = [{"params": rec.get("params"), "result": _result(rec)}]
            if "unauthorized" in hist[0]["result"] or "NOT_REGISTERED" in hist[0]["result"].upper().replace(" ", "_"):
                print(f"   {op['path']} 키 미등록 — 수리 대상 아님")
                continue
            for _ in range(ROUNDS):
                sug = _ask(op, hist, today)
                if not sug:
                    break
                tryp = {**extra, **sug["params"]}
                rec = deep.call_op(client, base, op, key, 100, extra=tryp)
                hist.append({"params": rec.get("params"), "result": _result(rec)})
                if rec["ok"]:
                    fixed[op["path"]] = {"params": {k: v for k, v in sug["params"].items()}, "why": sug["why"], "rows": rec["rows"]}
                    break
    if not fixed and any_ok:
        return {}  # 이미 되는 상태 (지난 수리분·승인 완료) — 실측만 다시
    return fixed or None


def _write_overrides(dsid: str, title: str, fixed: dict) -> None:
    """probe_params_auto.yaml에 덧붙인다 (주석으로 근거). 사람이 쓴 probe_params.yaml은 건드리지 않는다."""
    import yaml
    path = deep.OVERRIDES_AUTO
    if not path.exists():
        path.write_text("# 자동 수리 파라미터 (pds.probe.repair) — LLM이 명세·오류를 보고 제안하고, 실제 호출로 행이 나온 값만. probe_params.yaml 위에 덮는다.\n",
                        encoding="utf-8")
    cur = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if dsid in cur:
        return
    ops = {p: v["params"] for p, v in fixed.items()}
    why = " / ".join(f"{p}: {v['why']}" for p, v in fixed.items())
    line = yaml.safe_dump({dsid: ops}, allow_unicode=True, default_flow_style=None, width=400).strip()
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n# {title[:40]} — 자동 수리({MODEL}, 호출로 확인): {why[:200]}\n{line}\n")


def main(ids: list[str] | None = None) -> dict:
    sys.stdout.reconfigure(encoding="utf-8")
    tpath = config.KNOWLEDGE / "targets.json"
    targets = json.loads(tpath.read_text(encoding="utf-8"))
    todo = [t for t in targets if (t["id"] in ids if ids else t["status"] == "failed" and t["kind"] == "REST")]
    print(f"수리 대상 {len(todo)}")
    ok = []
    import threading
    from concurrent.futures import ThreadPoolExecutor
    lock = threading.Lock()  # 자동값 파일 쓰기는 한 번에 하나

    def one(t):
        try:
            fixed = repair_one(t["id"])
        except Exception as e:  # noqa: BLE001
            print(f"  {t['id']} 오류 {type(e).__name__}: {str(e)[:100]}", flush=True)
            return
        if fixed is not None:
            if fixed:
                with lock:
                    _write_overrides(t["id"], t["title"], fixed)
            try:
                run = deep.run_one(t["id"])  # 정식 실측 기록 (runs·stats·data)
            except Exception as e:  # noqa: BLE001
                print(f"  {t['id']} 실측 기록 오류 {type(e).__name__}: {str(e)[:100]}", flush=True)
                run = {}
            if run.get("ok_ops"):
                t["status"] = "verified"
                t["note"] = (t.get("note") or "") + " · 파라미터 자동 수리"
                ok.append(t["id"])
        print(f"  {t['id']} {'성공' if t['id'] in ok else '실패'} {t['title'][:40]}", flush=True)

    with ThreadPoolExecutor(int(os.environ.get("PDS_REPAIR_WORKERS", "8"))) as ex:
        list(ex.map(one, todo))
    tpath.write_text(json.dumps(targets, ensure_ascii=False, indent=1), encoding="utf-8")
    print({"대상": len(todo), "성공": len(ok)})
    return {"ok": ok}


if __name__ == "__main__":
    main(sys.argv[1:] or None)
