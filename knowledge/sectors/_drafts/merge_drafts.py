"""부문 검토 초안을 공유 지식 파일에 병합한다 (순서 = 인자 순서 = 재배치 규칙 우선순위).

사용: python knowledge/sectors/_drafts/merge_drafts.py A.yaml B.yaml ... [--dry]
  sector_map·exclusions·subsectors: 뒤에 붙임 (id·sector 중복이면 중단)
  keys·key_issuers·contexts: 새 id만 추가 (key_issuers는 catch-all data.go.kr 앞에), add_members: 기존 context에 멤버 추가
  review_log: _review_log.md 끝에 붙임
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

K = Path(__file__).resolve().parents[1].parent  # knowledge/
S = K / "sectors"


def _load(p: Path):
    return yaml.safe_load(p.read_text(encoding="utf-8")) or []


class _NoAlias(yaml.SafeDumper):
    """같은 객체를 여러 번 써도 앵커(&id001)를 만들지 않는다 — 파일 끝에 덧붙일 때 앵커 이름이 충돌한다."""
    def ignore_aliases(self, data):
        return True


def _dump(items) -> str:
    return yaml.dump(items, Dumper=_NoAlias, allow_unicode=True, sort_keys=False, width=250)


def main(argv):
    dry = "--dry" in argv
    drafts = [Path(a) for a in argv if a != "--dry"]
    smap, rules, subs = _load(S / "sector_map.yaml"), _load(S / "exclusions.yaml"), _load(S / "subsectors.yaml")
    keys, issuers, ctx = _load(K / "keys.yaml"), _load(K / "key_issuers.yaml"), _load(S / "contexts.yaml")
    ids = {r["id"] for r in smap} | {r["id"] for r in rules}
    secs = {s["sector"] for s in subs}
    add = {"sector_map": [], "exclusions": [], "subsectors": [], "keys": [], "key_issuers": [], "contexts": []}
    members: dict[str, list] = {}
    log = []
    for p in drafts:
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if isinstance(d.get("contexts"), dict):  # {new: [...], add_members: {...}} 형태도 받는다
            c = d.pop("contexts")
            d["contexts"] = c.get("new") or []
            d["add_members"] = {**(d.get("add_members") or {}), **(c.get("add_members") or {})}
        for kind in ("sector_map", "exclusions"):
            for r in d.get(kind) or []:
                assert r["id"] not in ids, f"{p.name}: duplicate rule id {r['id']}"
                ids.add(r["id"])
                add[kind].append(r)
        for s in d.get("subsectors") or []:
            assert s["sector"] not in secs, f"{p.name}: subsectors already defined for {s['sector']}"
            secs.add(s["sector"])
            add["subsectors"].append(s)
        known = {k["id"] for k in keys + add["keys"]}
        add["keys"] += [k for k in d.get("keys") or [] if k["id"] not in known]
        known = {k["id"] for k in issuers + add["key_issuers"]}
        add["key_issuers"] += [k for k in d.get("key_issuers") or [] if k["id"] not in known]
        known = {c["id"] for c in ctx + add["contexts"]}
        add["contexts"] += [c for c in d.get("contexts") or [] if c["id"] not in known]
        for cid, ms in (d.get("add_members") or {}).items():
            members.setdefault(cid, []).extend(ms)
        if d.get("review_log"):
            log.append(d["review_log"].rstrip() + "\n")
        print(p.name, {k: len(d.get(k) or []) for k in ("sector_map", "exclusions", "subsectors", "keys", "key_issuers", "contexts")})
    for c in ctx + add["contexts"]:
        for m in members.pop(c["id"], []):
            if m not in c["members"]:
                c["members"].append(m)
    assert not members, f"add_members for unknown contexts: {list(members)}"
    if dry:
        print("dry run", {k: len(v) for k, v in add.items()})
        return
    with open(S / "sector_map.yaml", "a", encoding="utf-8") as f:
        f.write(_dump(add["sector_map"]) if add["sector_map"] else "")
    with open(S / "exclusions.yaml", "a", encoding="utf-8") as f:
        f.write(_dump(add["exclusions"]) if add["exclusions"] else "")
    if add["subsectors"]:
        with open(S / "subsectors.yaml", "a", encoding="utf-8") as f:
            f.write("\n" + _dump(add["subsectors"]))
    if add["keys"]:
        with open(K / "keys.yaml", "a", encoding="utf-8") as f:
            f.write(_dump(add["keys"]))
    if add["key_issuers"]:
        text = (K / "key_issuers.yaml").read_text(encoding="utf-8")
        i = text.index("- id: data.go.kr\n")
        (K / "key_issuers.yaml").write_text(text[:i] + _dump(add["key_issuers"]) + text[i:], encoding="utf-8")
    # contexts: 머리 주석을 지키기 위해 본문만 다시 쓴다
    text = (S / "contexts.yaml").read_text(encoding="utf-8")
    head = text[:text.index("- id: ")]
    (S / "contexts.yaml").write_text(head + _dump(ctx + add["contexts"]), encoding="utf-8")
    if log:
        with open(S / "_review_log.md", "a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(log))
    print("merged", {k: len(v) for k, v in add.items()})


if __name__ == "__main__":
    main(sys.argv[1:])
