"""프로젝트 제외 규칙(knowledge/sectors/exclusions.yaml)과 부문 재배치(knowledge/sectors/sector_map.yaml).

조건(cond) 문법 — 한 dict 안의 조건은 모두 만족(AND):
  <컬럼>: 값 또는 값 목록   → 컬럼 값이 그중 하나
  title_regex: 정규식        → 제목이 정규식에 걸림
규칙:
  match / match_any: 제외 대상 (match는 cond 하나, match_any는 cond 목록 중 하나라도)
  keep / keep_any:   그중 살릴 것
"""
from __future__ import annotations

import re

import pandas as pd
import yaml

from pds import config

RULES = config.KNOWLEDGE / "sectors" / "exclusions.yaml"
SECTOR_MAP = config.KNOWLEDGE / "sectors" / "sector_map.yaml"


def _load(path) -> list[dict]:
    if not path.exists():
        return []
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def load_rules() -> list[dict]:
    return _load(RULES)


def load_sector_map() -> list[dict]:
    return _load(SECTOR_MAP)


def _shape_cols(df: pd.DataFrame, name: str) -> pd.Series:
    """연계 키·입도 판정을 규칙에서 쓸 수 있게 캐시 (pds/rank/shape.py와 같은 판정)."""
    cache = df.attrs.setdefault("_shape", {})
    if name not in cache:
        from pds.rank.shape import granularity, linkable
        cols = {c: df[c] if c in df.columns else pd.Series(None, index=df.index) for c in ("title", "output_cols", "request_vars")}
        if name == "keys":
            cache[name] = pd.Series([set(linkable(t, o, r)[1].split(",")) for t, o, r in
                                     zip(cols["title"], cols["output_cols"], cols["request_vars"])], index=df.index)
        else:
            cache[name] = pd.Series([granularity(t, o)[0] for t, o in zip(cols["title"], cols["output_cols"])],
                                    index=df.index)
    return cache[name]


def _cond(df: pd.DataFrame, cond: dict) -> pd.Series:
    """조건 dict (모두 만족). 특수 키: title_regex, agency_regex,
    has_key_any(연계 키 판정 이름 중 하나라도), granularity_gt(입도 점수 초과 = 집계·통계 아님),
    granularity_le(입도 점수 이하 = 집계·통계)."""
    m = pd.Series(True, index=df.index)
    for col, val in cond.items():
        if col == "agency_regex":
            rx = re.compile(val)
            m &= df["agency_name"].map(lambda t: bool(rx.search(t)) if isinstance(t, str) else False).astype(bool)
        elif col == "has_key_any":
            want = set(val)
            m &= _shape_cols(df, "keys").map(lambda ks: bool(ks & want)).astype(bool)
        elif col == "granularity_gt":
            m &= _shape_cols(df, "granularity") > float(val)
        elif col == "granularity_le":
            m &= _shape_cols(df, "granularity") <= float(val)
        elif col == "title_regex":
            rx = re.compile(val)
            m &= df["title"].map(lambda t: bool(rx.search(t)) if isinstance(t, str) else False).astype(bool)
        elif col not in df.columns:  # 규칙이 쓰는 컬럼이 없으면 그 조건은 불일치
            m &= False
        else:
            m &= df[col].isin(val if isinstance(val, list) else [val])
    return m


def _any(df: pd.DataFrame, conds: list[dict]) -> pd.Series:
    m = pd.Series(False, index=df.index)
    for c in conds:
        m |= _cond(df, c)
    return m


def _selector(df: pd.DataFrame, rule: dict, single: str, many: str, default: bool) -> pd.Series:
    if single in rule:
        return _cond(df, rule[single])
    if many in rule:
        return _any(df, rule[many])
    return pd.Series(default, index=df.index)


def excluded_by(df: pd.DataFrame, rules: list[dict] | None = None) -> pd.Series:
    """행마다 제외 규칙 id (없으면 None). df에는 규칙이 쓰는 컬럼(sector, agency_name, title …)이 있어야 한다."""
    rules = load_rules() if rules is None else rules
    out = pd.Series(None, index=df.index, dtype=object)
    for r in rules:
        hit = _selector(df, r, "match", "match_any", False)
        hit &= ~_selector(df, r, "keep", "keep_any", False)
        out[hit & out.isna()] = r["id"]
    return out


def remap_sector(df: pd.DataFrame, rules: list[dict] | None = None) -> tuple[pd.Series, pd.Series]:
    """(새 sector, 적용된 규칙 id). 첫 번째로 맞는 규칙이 이긴다."""
    rules = load_sector_map() if rules is None else rules
    sector = df["sector"].copy()
    rule_id = pd.Series(None, index=df.index, dtype=object)
    for r in rules:
        hit = _selector(df, r, "match", "match_any", False) & rule_id.isna()
        sector[hit] = r["set_sector"]
        rule_id[hit] = r["id"]
    return sector, rule_id


SUBSECTORS = config.KNOWLEDGE / "sectors" / "subsectors.yaml"


def load_subsectors() -> list[dict]:
    return _load(SUBSECTORS)


def assign_subsector(df: pd.DataFrame, defs: list[dict] | None = None) -> pd.DataFrame:
    """세부 부문 배정 → DataFrame(subsector, subsector_name, subsector_depth, cycle_override, last_event).
    df에는 sector(재배치 후)와 규칙이 쓰는 컬럼이 있어야 한다. 세부 부문이 정의되지 않은 부문은 전부 None."""
    defs = load_subsectors() if defs is None else defs
    cols = ["subsector", "subsector_name", "subsector_depth", "cycle_override", "last_event", "cross_cutting",
            "novelty", "value_source", "granularity_floor"]
    out = pd.DataFrame(None, index=df.index, columns=cols, dtype=object)
    for sdef in defs:
        in_sector = df["sector"].eq(sdef["sector"])
        todo = in_sector.copy()
        for sub in sdef["subsectors"]:
            hit = todo & _selector(df, sub, "match", "match_any", False)
            out.loc[hit, cols] = [sub["slug"], sub["name"], sub.get("depth"), sub.get("cycle"),
                                  str(sub["last_event"]) if sub.get("last_event") else None,
                                  bool(sub.get("cross_cutting", False)),
                                  sub.get("novelty", sdef.get("novelty")), sub.get("value_source"),
                                  sub.get("granularity_floor")]
            todo &= ~hit
        d = sdef.get("default")
        if d:
            out.loc[todo, cols] = [d["slug"], d["name"], d.get("depth"), None, None, False, d.get("novelty"), None, None]
        elif sdef.get("novelty"):  # 세부 부문 없이 부문 전체에 시의성만 지정 (예: 정부조달)
            out.loc[todo, "novelty"] = sdef["novelty"]
    return out
