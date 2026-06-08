"""강세 vs 약세 토론 리포트 생성.

Groq llama-3.3-70b 1회 호출로 강세론·약세론 동시 생성.
watchlist_batch.maybe_regen_debate() 에서 호출 — 직접 실행 금지.
"""

import logging
import os
import re

import httpx

from app.scoring.engine import EngineResult

log = logging.getLogger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"
_MAX_TOKENS = 800
_TIMEOUT = 30.0

_SYSTEM = """한국어로만 작성. 한자·베트남어·일본어 금지(티커 영문 허용).
당신은 두 명의 애널리스트다.
- 강세론자: 이 종목의 성장·상승 논거를 evidence 근거로 제시.
- 약세론자: 리스크·하락·과열 논거를 evidence 근거로 제시.
규칙:
- 직접 매수/매도 권유 금지. "주목할 만함" / "유의 필요" 식 완곡 표현.
- 반드시 제공된 evidence 수치를 인용. 없는 데이터 추정 금지.
- 각 4~6문장. 출력 형식:
===강세===
<강세론>
===약세===
<약세론>"""

# CJK 후처리 — chat/route.ts 정규식과 동일
_RE_CJK = re.compile(r"[一-鿿぀-ヿ＀-￯㐀-䶿]+")
_RE_VIET = re.compile(r"[Ạ-ỹ]")
_RE_LONE_EN = re.compile(r"(?<![A-Z0-9$%])([a-z]{2,})(?![a-z])")


def _clean(text: str) -> str:
    text = _RE_CJK.sub("", text)
    text = _RE_VIET.sub("", text)
    text = _RE_LONE_EN.sub("", text)
    return text.strip()


def _build_user_prompt(ticker: str, result: EngineResult) -> str:
    mr = result.module_results

    def score_of(name: str) -> str:
        r = mr.get(name)
        return f"{r.score:.0f}점" if r else "N/A"

    def ev(name: str) -> dict:
        r = mr.get(name)
        return r.evidence if r else {}

    rev = ev("revenue")
    an = ev("analyst")

    evidence_lines: list[str] = []
    if rev.get("sales_qoq_pct") is not None:
        evidence_lines.append(f"매출QoQ {float(rev['sales_qoq_pct']):+.1f}%")
    if rev.get("eps_qoq_pct") is not None:
        evidence_lines.append(f"EPSQoQ {float(rev['eps_qoq_pct']):+.1f}%")
    if rev.get("gross_margin_pct") is not None:
        evidence_lines.append(f"매출총이익률 {float(rev['gross_margin_pct']):.1f}%")
    if an.get("upside_pct") is not None:
        evidence_lines.append(f"상승여력 {float(an['upside_pct']):+.1f}%")
    if an.get("target_price") is not None:
        evidence_lines.append(f"목표가 ${float(an['target_price']):.0f}")
    if an.get("current_price") is not None:
        evidence_lines.append(f"현재가 ${float(an['current_price']):.0f}")

    conf_pct = int(result.confidence * 100)
    return (
        f"[종목] {ticker} / 총점 {result.total_score:.1f}({result.signal}) / 신뢰도 {conf_pct}%\n"
        f"[모듈별] 매출성장 {score_of('revenue')}, ETF흐름 {score_of('etf')}, "
        f"애널리스트 {score_of('analyst')}, 시총 {score_of('size')}, "
        f"모멘텀 {score_of('momentum')}, 버즈 {score_of('buzz')}, "
        f"내부자 {score_of('insider')}, 의회 {score_of('congress')}\n"
        f"[핵심 evidence] {', '.join(evidence_lines) or '데이터 없음'}"
    )


def _parse(raw: str) -> tuple[str, str]:
    """===강세=== / ===약세=== 구분자로 분리."""
    bull = bear = ""
    parts = re.split(r"===강세===|===약세===", raw)
    # parts[0]=앞부분, parts[1]=강세, parts[2]=약세 (구분자 개수에 따라 달라짐)
    if len(parts) >= 3:
        bull = _clean(parts[1])
        bear = _clean(parts[2])
    elif len(parts) == 2:
        # 구분자 1개만 있는 경우 방어
        combined = _clean(parts[1])
        half = len(combined) // 2
        bull, bear = combined[:half], combined[half:]
    return bull, bear


def generate_debate(ticker: str, result: EngineResult) -> tuple[str, str]:
    """Groq 호출 → (bull_text, bear_text). 실패 시 ("", "") 반환(graceful)."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        log.warning("[%s] GROQ_API_KEY 없음 — 토론 생성 스킵", ticker)
        return "", ""

    user_prompt = _build_user_prompt(ticker, result)
    payload = {
        "model": _MODEL,
        "max_tokens": _MAX_TOKENS,
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    }

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(
                _GROQ_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        bull, bear = _parse(raw)
        if not bull or not bear:
            log.warning("[%s] 토론 파싱 실패 (구분자 없음) — 스킵", ticker)
            return "", ""
        log.info("[%s] 토론 생성 완료 (bull=%d자, bear=%d자)", ticker, len(bull), len(bear))
        return bull, bear
    except Exception as e:
        log.error("[%s] 토론 생성 실패: %s", ticker, e)
        return "", ""
