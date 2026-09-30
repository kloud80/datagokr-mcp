"""지식 원본 읽기·쓰기 — knowledge/ 아래 엔티티 파일의 위치를 아는 유일한 곳.

읽기는 원본(dict)과 파일 경로를 함께 돌려준다(검증 오류 위치 표시용). 모델 변환은 validate가 한다.
쓰기는 ruamel.yaml(주석·순서 보존, 숫자처럼 보이는 문자열은 따옴표).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Iterator

from ruamel.yaml import YAML

from pds import config

K = config.KNOWLEDGE
PATHS = {
    "key": K / "keys",               # {id}.yaml
    "context": K / "contexts",       # {id}.yaml
    "mapping": K / "mappings",       # {a}__{b}.yaml (+ .parquet)
    "recipe": K / "recipes",         # {slug}.yaml
    "law": K / "laws",               # {law_id}.yaml
    "code": K / "codes",             # {id}.yaml (+ .parquet)
    "dataset": K / "datasets",       # {정책분야}/{id}.yaml
    "edge": K / "edges.yaml",        # 목록 한 파일
    "gap": K / "gaps.yaml",          # 목록 한 파일
    "issuer": K / "key_issuers.yaml",  # 목록 한 파일
    "target": K / "targets.json",    # 목록 한 파일
}


def rel(p: Path) -> str:
    try:
        return p.relative_to(config.ROOT).as_posix()
    except ValueError:  # 리포 밖 (테스트 임시 경로 등)
        return p.as_posix()


_SAFE = YAML(typ="safe", pure=True)


def _load(p: Path):
    """쓰기(ruamel, YAML 1.2)와 같은 판본으로 읽는다 — PyYAML(1.1)은 '09:00'을 숫자로, 'Y'·'no'를 불리언으로 읽는다."""
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    return _SAFE.load(p.read_text(encoding="utf-8"))


def iter_raw(kind: str) -> Iterator[tuple[dict, Path]]:
    """(원본 dict, 파일) — 디렉터리형은 파일마다 1건, 목록형은 항목마다."""
    p = PATHS[kind]
    if p.is_dir():
        pattern = "**/*.yaml" if kind == "dataset" else "*.yaml"
        for f in sorted(p.glob(pattern)):
            if not f.name.startswith("_"):
                yield _load(f) or {}, f
    elif p.exists():
        for item in _load(p) or []:
            yield item, p


def read(p: Path):
    return _load(p)


def load(kind: str) -> list[dict]:
    return [d for d, _ in iter_raw(kind)]


def dataset_path(sector: str, dsid: str) -> Path:
    field = sector.split("/")[0]
    return PATHS["dataset"] / field / f"{dsid.replace(':', '_')}.yaml"


def _yaml() -> YAML:
    y = YAML()
    y.allow_unicode = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    y.default_flow_style = False
    return y


def dump(data, path: Path, header: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    _yaml().dump(data, buf)
    text = buf.getvalue()
    if header:
        text = "".join(f"# {ln}\n" if ln else "#\n" for ln in header.splitlines()) + text
    path.write_text(text, encoding="utf-8")
    return path
