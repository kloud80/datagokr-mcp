"""claim → 사람이 읽는 배지. 화면에 claim id(c-15154916-03)를 그대로 보이지 않고 값을 짧게 풀어 쓴다.

tone: ok(갱신·검증) · inf(접근) · key(조인 키) · warn(주의) · neutral
id·근거 원문은 claims 목록으로 따로 내려 '근거 보기'를 펼칠 때만 보인다.
"""
from __future__ import annotations

import re

from pds.schema import GROUNDED

KIND_LABEL = {"access": "접근", "cadence": "갱신", "key": "조인 키", "coverage": "범위", "legal_basis": "법적 근거",
              "admin_note": "검토 메모", "pitfall": "주의", "domain_law": "관련 법"}


def _short(s: str, n: int = 30) -> str:
    s = re.split(r"(?<=[.。])\s|\s—\s", s.strip())[0]
    return s if len(s) <= n else s[: n - 1] + "…"


def rows(d: dict) -> int | None:
    for c in d.get("claims") or []:
        if c["kind"] == "coverage":
            m = re.search(r"전체 건수 ([\d,]+)", c["value"])
            if m:
                return int(m.group(1).replace(",", ""))
    return None


def badges(d: dict, access: dict) -> list[dict]:
    out = []
    claims = [c for c in d.get("claims") or [] if any(e["type"] in GROUNDED for e in c["evidence"])]
    by = {}
    for c in claims:
        by.setdefault(c["kind"], []).append(c)

    for c in by.get("cadence", [])[:1]:
        v = c["value"]
        m = re.search(r"최신 행 날짜 (\S+) \(관측일 기준 (\d+)일 전\)", v)
        if m:
            out.append({"label": f"최신 {m.group(1)} · {m.group(2)}일 전", "tone": "ok", "kind": "cadence"})
        elif v.startswith("주기 정보 없음"):
            out.append({"label": "갱신 주기 미확인", "tone": "neutral", "kind": "cadence"})
        else:
            out.append({"label": _short(v, 24), "tone": "ok", "kind": "cadence"})

    if access.get("channel") == "external":
        out.append({"label": f"외부 키 · {access.get('issuer') or '별도 발급'}", "tone": "inf", "kind": "access"})
    else:
        ap = {"auto": "자동승인", "manual": "심의승인"}.get(access.get("approval") or "", access.get("approval") or "활용신청")
        lim = access.get("daily_limit")
        out.append({"label": ap + (f" · 일 {lim:,}회" if isinstance(lim, int) else ""), "tone": "inf", "kind": "access"})

    for c in by.get("key", [])[:1]:
        keys = list(dict.fromkeys(re.findall(r"([a-z_]+)\(", c["value"])))
        if keys:
            out.append({"label": "키 " + "·".join(keys[:3]), "tone": "key", "kind": "key"})

    for c in by.get("coverage", [])[:1]:
        m = re.search(r"범위 (\S+)", c["value"])
        if m and m.group(1) not in ("-", "?", "미상"):
            out.append({"label": f"범위 {m.group(1)}", "tone": "neutral", "kind": "coverage"})

    for c in by.get("pitfall", [])[:1]:
        out.append({"label": _short(c["value"], 30), "tone": "warn", "kind": "pitfall"})
    return out


def claims_view(d: dict, limit: int = 12) -> list[dict]:
    """'근거 보기' — 근거 있는 claim만, 종류·값·근거 종류·날짜."""
    out = []
    for c in d.get("claims") or []:
        ev = [e for e in c["evidence"] if e["type"] in GROUNDED]
        if not ev:
            continue
        out.append({"id": c["id"], "kind": c["kind"], "kind_label": KIND_LABEL.get(c["kind"], c["kind"]),
                    "value": c["value"][:240], "evidence": sorted({e["type"] for e in ev}),
                    "date": next((str(e.get("date")) for e in ev if e.get("date")), None)})
    return out[:limit]
