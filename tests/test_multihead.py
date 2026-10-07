"""멀티헤드 규칙 부분 (LLM 없이) — 목록 필드명으로 단위 추정, 주제 간 연결, 헤드별 후보 돌려 고르기."""
from pds.strategy import multihead as m
from pds.strategy.plan import _head_picks


def test_cols_meta_crop_and_station():
    crop = m._cols_meta("10a당수량백미중,등숙비율,시험년도,지역명,지역코드 목록,nan", "농촌진흥청 국립식량과학원_벼 작황 성적 정보 서비스")
    assert crop["space"] == "sgg" and crop["time"] == "year" and crop["estimated"]
    wx = m._cols_meta("nan,nan", "기상청_종관기상관측 조회서비스")  # 필드 메타가 없으면 제목으로 지점 기반
    assert wx["space"] == "point" and wx["space_via"] == "station" and "station" in wx["keys"]
    shop = m._cols_meta("nan,nan", "농림축산검역본부_반려동물 영업장 주소 등 정보")
    assert shop["space"] == "point" and shop["space_via"] == "address"


def test_link_aligned_estimated():
    items = {"a": {"id": "a", "tier": "catalog"}, "b": {"id": "b", "tier": "catalog"}}
    metas = {"a": {"space": "sgg", "time": "year", "space_via": None, "keys": set(), "estimated": True},
             "b": {"space": "point", "time": "day", "space_via": "station", "keys": {"station"}, "estimated": True}}
    import networkx as nx
    lk = m.link("a", "b", items, metas, nx.Graph(), {})
    assert lk["kind"] == "aligned" and lk["estimated"] and lk["align"]["space"] == "sgg" and lk["align"]["time"] == "year"


def test_head_picks_round_robin_rep_first():
    mh = {"heads": [
        {"name": "작황", "rep": "c2", "picks": [{"id": "c1", "tier": "catalog", "score": 3, "fit": 0.9}, {"id": "c2", "tier": "catalog", "score": 3, "fit": 0.8},
                                                 {"id": "c3", "tier": "catalog", "score": 1, "fit": 0.9}]},
        {"name": "기상", "rep": "w1", "picks": [{"id": "w1", "tier": "catalog", "score": 3, "fit": 0.9}, {"id": "w2", "tier": "catalog", "score": 2, "fit": 0.5}]}]}
    got = [(p["id"], p["head"], p["rep"]) for p in _head_picks(mh, "catalog")]
    assert got == [("c2", "작황", True), ("w1", "기상", True), ("c1", "작황", False), ("w2", "기상", False)]  # 1점은 빠진다
