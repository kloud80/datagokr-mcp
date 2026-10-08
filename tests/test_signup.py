from pds.strategy import signup


def test_portal_needs_no_signup():
    assert signup.note("1", external=False) is None


def test_known_site_guide():
    n = signup.note("1", external=True, issuer="openapi.seoul.go.kr:8088")
    assert n["required"] and n["site"] == "서울 열린데이터광장" and "data.go.kr 활용신청과 별개" in n["text"]
    assert signup.note("1", external=True, issuer="www.vworld.kr")["site"].startswith("브이월드")


def test_file_site_without_signup_not_summarized():
    n = signup.note("1", external=True, issuer="file.localdata.go.kr")
    assert n["required"] is False
    p = {"datasets": [{"id": "1", "title": "a", "access": {"signup": n}}],
         "unverified_leads": [{"id": "2", "title": "b", "tier": "catalog",
                               "access": {"signup": signup.note("2", True, "apihub.kma.go.kr")}}]}
    g = signup.summarize(p)
    assert [x["site"] for x in g] == ["기상청 API허브"] and g[0]["datasets"][0]["tier"] == "catalog"


def test_catalog_link_is_external():
    assert signup.catalog_external({"api_type": "LINK"}) and not signup.catalog_external({"api_type": "REST"})
