"""포털 AI 비교 1천 문항 만들기 (Opus, 일회성) → questions.yaml

분야(포털 대분류 16 + 분야 넘나듦)마다 정해진 수를 질문 유형을 섞어 만든다. 유형:
  lookup   한 가지 데이터를 찾는 단순 조회 ("○○ 데이터 있어?")
  region   특정 지역(시도·시군구·동)을 짚은 질문
  combine  두세 가지 데이터를 이어야 답이 나오는 질문
  analysis 연구·정책·사업 목적의 분석 질문 (무엇을 보고 싶은지 서술)
  casual   일상 말투·모호한 질문 (데이터 이름을 모르는 사람)
  python -X utf8 -m evals.portal_1k.gen_questions
"""
from __future__ import annotations

import json
import pathlib
import re
from concurrent.futures import ThreadPoolExecutor

import yaml

from evals.portal_ai.judge import _json
from pds.service import llm

ROOT = pathlib.Path(__file__).resolve().parent
MODEL = "claude-opus-5-5"

SECTORS = {
    "국토관리": (90, "수자원·주택·지역및도시·산업단지·건축물·도시개발·정비·공간정보·토지이용규제·도시계획시설·공원녹지·국토·도시계획·토지·지적·지역발전"),
    "교통물류": (75, "도로·철도·물류·해운·항만·항공·공항·대중교통·자동차"),
    "산업고용": (75, "에너지·자원개발·산업·중소기업·고용노동·산업진흥·산업기술지원·원자력·통상·창업"),
    "보건의료": (70, "보건의료·건강보험·병원·약국·감염병·응급"),
    "공공행정": (70, "일반행정·지방행정·재정지원·국가통계·법제·국정운영·정부자원관리·공정거래·국정홍보·정부조달·국민권익·인권·선거"),
    "사회복지": (70, "사회복지일반·보육·가족·여성·노인·청소년·취약계층지원·공적연금·기초생활보장·장애인"),
    "환경기상": (70, "환경일반·폐기물·대기·자연·상하수도·수질·해양환경·기상·기후"),
    "문화관광": (65, "문화예술·관광·문화재·체육·도서관·공연·축제"),
    "농축수산": (65, "농업·농촌·축산·해양수산·어촌·임업·산촌·농산물 가격"),
    "재난안전": (65, "안전관리·경찰·해경·소방·재난·범죄·교통사고"),
    "교육": (60, "교육일반·평생교육·직업교육·유아·초중등교육·고등교육·학교·학원"),
    "재정금융": (55, "세제·재정·금융·산업금융·무역·투자유치·기업 공시·부동산 금융"),
    "식품건강": (50, "식품의약안전·식품 위생·의약품·건강기능식품·음식점"),
    "과학기술": (35, "과학기술연구·방송통신·우정·특허·R&D"),
    "통일외교안보": (30, "보훈·외교·병무·통일·국방"),
    "법률": (25, "법무·검찰·법령·판례·교정·출입국"),
    "분야 넘나듦": (30, "두 개 이상 대분류를 넘나드는 질문 (예: 기상+농업, 상권+교통, 복지+주거)"),
}
TYPES = "lookup 20% · region 20% · combine 25% · analysis 20% · casual 15%"

SYS = """너는 한국 공공데이터포털(data.go.kr) 이용자들의 실제 질문을 만드는 사람이다.
공공데이터를 찾는 다양한 사람(개인 사업자, 연구자, 공무원, 기자, 개발자, 학생, 일반 시민)이 AI 검색창에 칠 법한 질문을 만든다.
규칙:
- 한국어, 한 문장(5~60자 정도), 실제 사람이 치는 말투. 너무 교과서적이거나 똑같은 틀을 반복하지 않는다.
- 주어진 분야 안에서 세부 주제를 고르게 퍼뜨린다. 같은 데이터를 묻는 질문을 두 번 만들지 않는다.
- 유형 비율을 지킨다: """ + TYPES + """
  lookup=한 가지 데이터 찾기, region=특정 지역(시도·시군구·동네 이름)을 짚음, combine=두세 데이터를 이어야 답이 나옴,
  analysis=연구·정책·사업 목적의 분석, casual=데이터 이름을 모르는 일상 말투·모호한 질문
- 공공데이터로 답이 있을 법한 질문 위주로 하되, 10% 정도는 공공데이터로는 답하기 어려운 질문(개인정보·민간 데이터 필요)도 섞는다 (hard=true).
JSON만 출력: {"questions": [{"q": "...", "type": "lookup|region|combine|analysis|casual", "topic": "세부 주제 두세 단어", "hard": false}, ...]}"""


def batch(sector: str, sub: str, n: int, avoid: list[str], seed: int) -> list[dict]:
    user = (f"분야: {sector}\n세부 주제 예: {sub}\n질문 {n}개를 만들어라. (묶음 번호 {seed} — 다른 묶음과 겹치지 않게 세부 주제를 다르게 골라라)\n"
            + ("이미 만든 질문(겹치지 말 것):\n" + "\n".join(avoid[-80:]) if avoid else ""))
    r = llm.client().beta.messages.create(model=MODEL, max_tokens=8000, system=SYS, **llm.FALLBACK,
                                          messages=[{"role": "user", "content": user}])
    return (_json(llm._text(r)) or {}).get("questions") or []


def norm(q: str) -> str:
    return re.sub(r"[\s?.!,~]", "", q)


def sector_qs(item) -> list[dict]:
    sector, (n, sub) = item
    out, seen = [], set()
    k = 0
    while len(out) < n and k < 6:
        need = min(40, n - len(out) + 3)
        for x in batch(sector, sub, need, [o["q"] for o in out], k):
            if isinstance(x, dict) and x.get("q") and norm(x["q"]) not in seen:
                seen.add(norm(x["q"]))
                out.append({"q": x["q"].strip(), "type": x.get("type"), "topic": x.get("topic"), "hard": bool(x.get("hard")), "sector": sector})
        k += 1
        print(f"{sector} {len(out)}/{n}", flush=True)
    return out[:n]


if __name__ == "__main__":
    old = {norm(x["q"]) for x in yaml.safe_load((ROOT.parent / "portal_ai" / "questions.yaml").read_text(encoding="utf-8"))}
    with ThreadPoolExecutor(6) as ex:
        groups = list(ex.map(sector_qs, SECTORS.items()))
    rows, seen = [], set(old)
    for g in groups:
        for x in g:
            if norm(x["q"]) not in seen:
                seen.add(norm(x["q"]))
                rows.append(x)
    for i, x in enumerate(rows):
        x["id"] = f"k{i + 1:04d}"
    rows = [{"id": x["id"], **{k: v for k, v in x.items() if k != "id"}} for x in rows]
    (ROOT / "questions.yaml").write_text("# 포털 AI 비교 1천 문항 (Opus 생성, 2026-10-08) — gen_questions.py\n"
                                         + yaml.safe_dump(rows, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    from collections import Counter
    print(len(rows), Counter(x["sector"] for x in rows), Counter(x["type"] for x in rows), json.dumps(sum(x["hard"] for x in rows)))
