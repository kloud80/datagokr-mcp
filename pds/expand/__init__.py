"""지식 체계 확대 차수 — PDS_WAVE(기본 wave2)로 고른다. 차수마다 knowledge/expansion/<차수>/ 와 검증 라운드 번호."""
import os

from pds import config

WAVE = os.environ.get("PDS_WAVE", "wave2")
OUT = config.KNOWLEDGE / "expansion" / WAVE
ROUND = {"wave2": "4", "wave3": "5"}[WAVE]
