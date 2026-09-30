"""Edge 후보·실측 (KNOWLEDGE-SPEC §3.4, §7-5)."""
import pytest

from pds.edges.auto import _sig
from pds.probe.join import LAT, LON


def test_signature_ignores_confidence_and_id():
    a = {"id": "e-0001", "src": "1", "dst": "2", "rel": "joinable", "on": {"left": ["a"], "right": ["b"]}, "confidence": 0.5}
    b = {**a, "id": "e-0099", "confidence": 0.9}
    assert _sig(a) == _sig(b)
    assert _sig(a) != _sig({**a, "on": {"left": ["a"], "right": ["c"]}})


@pytest.mark.parametrize("col,lat,lon", [("lat", True, False), ("la_crd", True, False), ("lo_crd", False, True),
                                         ("WGS84_LAT", True, False), ("faci_lat", True, False), ("wgs84Lon", False, True),
                                         ("logitude", False, True), ("위도", True, False), ("경도", False, True)])
def test_coordinate_column_detection(col, lat, lon):
    assert bool(LAT.search(col)) == lat and bool(LON.search(col)) == lon


def test_repository_edges_reference_known_datasets():
    from pds.schema.validate import run
    rep, objs = run()
    assert not [e for e in rep.errors if e.startswith("edges.yaml")], rep.errors[:5]
    ids = [e.id for e in objs["edge"]]
    assert len(ids) == len(set(ids))
