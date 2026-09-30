"""data.go.kr 파일데이터 다운로드.

상세 페이지의 schema.org `contentUrl`은 엉뚱한 첨부(활용사례 이미지 등)를 가리킬 때가 있다(15062804에서 확인).
그래서 포털 JS(`fileDetailObj.fn_fileDataDown`)와 같은 경로를 쓴다:
  1) 상세 페이지에서 publicDataDetailPk(uddi:...) 추출
  2) POST /tcs/dss/selectFileDataDownload.do → 실제 atchFileId, 데이터명(날짜 포함)
  3) GET  /cmm/cmm/fileDownload.do?atchFileId=...
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from pds import config

BASE = "https://www.data.go.kr"
UA = {"User-Agent": "Mozilla/5.0 (pds-ingest)"}


def resolve_file(client: httpx.Client, dataset_id: str) -> dict:
    page = client.get(f"{BASE}/data/{dataset_id}/fileData.do").text
    m = re.search(r'id="publicDataDetailPk"[^>]*value="(uddi:[0-9a-f-]+)"', page)
    if not m:
        raise RuntimeError(f"{dataset_id}: publicDataDetailPk를 찾지 못함 (파일데이터가 아니거나 페이지 구조 변경)")
    resp = client.post(
        f"{BASE}/tcs/dss/selectFileDataDownload.do",
        data={
            "publicDataDetailPk": m.group(1),
            "publicDataPk": dataset_id,
            "atchFileId": "",
            "fileDetailSn": "1",
            "publicDataTyCode": "PR0051",
        },
    )
    body = json.loads(resp.text)
    if not body.get("status"):
        raise RuntimeError(f"{dataset_id}: 다운로드 정보 조회 실패: {body.get('error')}")
    info = body["dataSetFileDetailInfo"]
    return {
        "dataset_id": dataset_id,
        "detail_pk": m.group(1),
        "atch_file_id": body["atchFileId"],
        "file_detail_sn": body["fileDetailSn"],
        "data_name": info.get("dataNm"),
        "updated_at": info.get("updtDt"),
    }


def download(dataset_id: str, dest_dir: Path = config.RAW) -> Path:
    prefix, _ = config.BULK_SOURCES[dataset_id]
    dest_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=UA, timeout=120, follow_redirects=True) as client:
        info = resolve_file(client, dataset_id)
        # 데이터명 끝의 _YYYYMMDD가 스냅샷 기준일
        m = re.search(r"_(\d{8})\s*$", info["data_name"] or "")
        snap = m.group(1) if m else info["updated_at"][:10].replace("-", "")
        out = dest_dir / f"{prefix}_{dataset_id}_{snap}.csv"
        if out.exists():
            return out
        url = f"{BASE}/cmm/cmm/fileDownload.do"
        params = {"atchFileId": info["atch_file_id"], "fileDetailSn": info["file_detail_sn"], "insertDataPrcus": "N"}
        tmp = out.with_suffix(".part")
        with client.stream("GET", url, params=params) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        tmp.replace(out)
        out.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        return out


def download_all() -> list[Path]:
    return [download(i) for i in config.BULK_SOURCES]
