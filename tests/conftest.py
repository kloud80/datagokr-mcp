"""테스트는 규칙 경로로 — 멀티헤드 전략(LLM 호출)은 끄고 결정적인 검색·조합만 잰다. 멀티헤드는 evals/portal_ai/judge_heads.py로 평가."""
import os

os.environ.setdefault("PDS_HEADS", "0")
