"""위키 승인 반영 — 실제 데이터셋 yaml 사본에 써 보고, 스키마 통과·머리 주석 유지·재생성 보존 형태를 본다."""
import shutil
from types import SimpleNamespace

import pytest

from pds.schema import store
from pds.service import wiki

DSID = "15004506"


@pytest.fixture
def ix(tmp_path, monkeypatch):
    src = next(store.PATHS["dataset"].glob(f"*/{DSID}.yaml"))
    dst = tmp_path / src.parent.name / src.name
    dst.parent.mkdir()
    shutil.copy(src, dst)
    monkeypatch.setattr(store, "dataset_path", lambda sector, dsid: dst)
    monkeypatch.setattr(wiki.config, "ROOT", tmp_path)
    return SimpleNamespace(datasets={DSID: store.read(dst)}, path=dst)


def _p(kind, value, target=None, pid=1):
    return {"id": pid, "dataset_id": DSID, "kind": kind, "target": target, "proposed_value": value, "author": "홍길동", "reason": "현장 확인"}


def test_summary_and_header(ix):
    out = wiki.apply(ix, _p("summary", "새 설명"), "구름")
    d = store.read(ix.path)
    assert d["summary_user"] == "새 설명" and d["review"]["by"] == "구름" and out["field"] == "summary_user"
    text = ix.path.read_text(encoding="utf-8")
    assert text.count("# Dataset 15004506") == 1  # 머리 주석이 겹치지 않는다
    assert ix.datasets[DSID]["summary_user"] == "새 설명"


def test_synonym_dedup(ix):
    wiki.apply(ix, _p("synonym", "마을회관, 새말,새말"), "구름")
    syn = store.read(ix.path)["synonyms"]
    assert syn.count("마을회관") == 1 and syn.count("새말") == 1


def test_relation_claim_preserved_shape(ix):
    out = wiki.apply(ix, _p("relation", "주소로 이어진다", target="15012005", pid=7), "구름")
    d = store.read(ix.path)
    c = next(c for c in d["claims"] if c["id"] == out["claim"])
    assert c["kind"] == "admin_note" and c["evidence"][0]["type"] == "admin_review"
    assert c["evidence"][0]["source"] == "wiki:proposal/7"
    assert "generated_by" not in c["qualifiers"]  # gen-dataset이 보존하는 claim
    assert "15012005" in d["edges_hint"]


def test_reviewer_token(monkeypatch):
    monkeypatch.setenv("WIKI_ADMIN_TOKENS", "구름:abc, 대표:xyz")
    assert wiki.reviewer_of("xyz") == "대표"
    assert wiki.reviewer_of("nope") is None and wiki.reviewer_of(None) is None


def test_keys_codes_pages():
    """실제 색인 — 키·코드표 목록과 문서가 서로 이어진다."""
    from pds.service import index
    ix = index.get()
    keys = {k["id"]: k for k in wiki.keys_list(ix)}
    assert len(keys) == len(ix.keys) and keys["bizno"]["datasets"] > 0
    kp = wiki.key_page(ix, "bizno")
    assert kp["total"] == keys["bizno"]["datasets"] and all("fields" in r for r in kp["rows"])
    codes = {c["id"]: c for c in wiki.codes_list(ix)}
    assert len(codes) == len(ix.codes)
    cp = wiki.code_page(ix, "hira_cl_cd")
    assert any(u["id"] == "15001698" and "clCd" in u["fields"] for u in cp["used_by"]) and cp["values"]
    assert wiki.code_page(ix, "없는코드") is None
