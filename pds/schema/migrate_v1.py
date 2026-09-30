"""일회성 마이그레이션 v1 (2026-09-30) — Phase 1 지식 파일을 KNOWLEDGE-SPEC 엔티티 배치로 옮긴다.

  keys.yaml               → knowledge/keys/{id}.yaml       (format→pattern 추출, master→master_datasets, parent/children→related_keys)
  sectors/contexts.yaml   → knowledge/contexts/{id}.yaml   (requires_mappings·recipe 필드 추가)
  subsectors.yaml gaps:   → knowledge/gaps.yaml            (subsectors.yaml에서는 gaps 블록 제거)
  옛 파일은 knowledge/_superseded/로 옮긴다 (삭제하지 않음).

멱등이 아니다 — 옛 파일이 _superseded로 옮겨진 뒤에는 할 일이 없다고 보고 끝낸다.
"""
from __future__ import annotations

import re
import shutil

import yaml

from pds import config
from pds.schema import store

K = config.KNOWLEDGE
SUP = K / "_superseded"

# 키 사이 관계 보강 (기존 parent/children 외에 형식상 명백한 것만)
EXTRA_RELATED = {
    "pnu": [{"key": "bjd_cd", "relation": "prefix", "note": "PNU 앞 10자리 = 법정동코드"}],
    "sgg_cd": [{"key": "bjd_cd", "relation": "prefix", "note": "법정동코드 앞 5자리 = 시군구코드"}],
    "neis_school_cd": [{"key": "school_cd", "relation": "parent", "note": "school_cd 3체계 중 나이스·학교기본정보 표준코드"}],
}
COMPOSED = {"pnu": ["bjd_cd", "산구분(1)", "본번(4)", "부번(4)"]}
# gaps note에서 읽히는 포털 밖 대안 (사람이 note에 적어 둔 것만)
GAP_EXTERNAL = {
    "political-finance": "중앙선거관리위원회 정치자금 공개 시스템 (포털 밖)",
    "regulation": "국무조정실 규제정보포털 등록규제",
    "audit-ethics": "감사원 감사결과 공개 (감사원 누리집) · 공직자 재산공개는 관보 API로 gazette-notice에 있음",
    "rnd-announcements": "IRIS 범부처통합연구지원시스템 사업공고",
}


def _pattern(fmt: str | None) -> str | None:
    if not fmt:
        return None
    m = re.match(r"^(\^\S+\$)(\s|$)", fmt.strip())
    if m and "/" not in fmt:
        return m.group(1)
    return None


def migrate_keys() -> int:
    src = K / "keys.yaml"
    keys = yaml.safe_load(src.read_text(encoding="utf-8"))
    for k in keys:
        rel = [{"key": k["parent"], "relation": "parent"}] if k.get("parent") else []
        rel += [{"key": c, "relation": "child"} for c in k.get("children", [])]
        rel += [r for r in EXTRA_RELATED.get(k["id"], []) if r["key"] not in {x["key"] for x in rel}]
        out = {"id": k["id"], "name": k["name"], "type": "natural", "scope": k.get("scope", "global"),
               "format": k.get("format"), "pattern": _pattern(k.get("format")),
               "master_datasets": [str(m) for m in k.get("master", [])], "composed_of": COMPOSED.get(k["id"], []),
               "related_keys": rel, "shape_names": k.get("shape_names", []), "notes": k.get("note")}
        store.dump({x: v for x, v in out.items() if v not in (None, [], {})} | {"id": k["id"]},
                   store.PATHS["key"] / f"{k['id']}.yaml")
    return len(keys)


def migrate_contexts() -> int:
    src = K / "sectors" / "contexts.yaml"
    ctx = yaml.safe_load(src.read_text(encoding="utf-8"))
    for c in ctx:
        out = {"id": c["id"], "name": c["name"], "dimension": c["dimension"], "question": c.get("question"),
               "note": (c.get("note") or "").strip() or None, "key": c.get("key"), "members": c["members"],
               "requires_mappings": [], "recipe": None, "decided_at": "2026-09-29", "decided_by": "구름"}
        store.dump({x: v for x, v in out.items() if v is not None}, store.PATHS["context"] / f"{c['id']}.yaml")
    return len(ctx)


def migrate_gaps() -> int:
    path = K / "sectors" / "subsectors.yaml"
    subs = yaml.safe_load(path.read_text(encoding="utf-8"))
    gaps = []
    for s in subs:
        f, a = s["sector"].split(" - ", 1)
        for g in s.get("gaps") or []:
            note = g.get("note", "")
            resolved = note.startswith("해소")
            gaps.append({"id": f"{f}/{a}/{g['slug']}", "sector": s["sector"], "name": g["name"], "reason": note,
                         "external_candidate": GAP_EXTERNAL.get(g["slug"]), "status": "resolved" if resolved else "open",
                         "resolved_by": "과학기술 - 우정/address-master" if resolved else None,
                         "decided_at": str(s.get("decided_at")), "decided_by": s.get("decided_by")})
    store.dump([{k: v for k, v in g.items() if v is not None} for g in gaps], store.PATHS["gap"],
               header="공백(gap) — 포털에 데이터가 없는 업무 영역. 전략 응답 gaps[]의 원천 (KNOWLEDGE-SPEC §9-1).\n"
                      "2026-09-30 subsectors.yaml의 gaps 블록에서 옮김 (pds/schema/migrate_v1.py).")
    # subsectors.yaml에서 gaps 블록 제거 (텍스트 편집 — 나머지 서식·주석 보존)
    text = path.read_text(encoding="utf-8")
    new = re.sub(r"\n  gaps:\n(?:    - \{.*\}\n)+", "\n", text)
    assert new.count("\n  gaps:") == 0, "gaps 블록 제거 실패"
    path.write_text(new, encoding="utf-8")
    return len(gaps)


def run() -> dict:
    if (SUP / "keys.yaml").exists():
        return {"skipped": "이미 옮겨짐 (knowledge/_superseded/)"}
    out = {"keys": migrate_keys(), "contexts": migrate_contexts(), "gaps": migrate_gaps()}
    SUP.mkdir(exist_ok=True)
    for p in (K / "keys.yaml", K / "sectors" / "contexts.yaml", K / "sectors" / "contexts.md"):
        if p.exists():
            shutil.move(str(p), SUP / p.name)
    (SUP / "README.md").write_text(
        "# 대체된 원본 (2026-09-30)\n\nKNOWLEDGE-SPEC 엔티티 배치로 옮긴 뒤의 옛 파일. 읽는 코드는 없다. 첫 커밋 이후 지워도 된다.\n\n"
        "| 옛 파일 | 새 위치 |\n|---|---|\n| keys.yaml | knowledge/keys/{id}.yaml |\n"
        "| contexts.yaml · contexts.md | knowledge/contexts/{id}.yaml |\n| subsectors.yaml `gaps:` | knowledge/gaps.yaml |\n",
        encoding="utf-8")
    return out


if __name__ == "__main__":
    print(run())
