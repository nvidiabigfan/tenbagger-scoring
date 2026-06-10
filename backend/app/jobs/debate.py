"""멀티에이전트 강세 vs 약세 토론 리포트 생성.

Groq(강세) vs Gemini(약세) 2라운드 반박 토론 후 Groq 심판 판정.
watchlist_batch._maybe_regen_debate() 에서 호출 — 직접 실행 금지.

인터페이스: generate_debate(ticker, result) → (bull_text, bear_text)
"""

import asyncio
import json
import logging
import os
import re
import uuid

import httpx

from app.db import client as db
from app.scoring.engine import EngineResult

log = logging.getLogger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"
_GEMINI_MODEL = "gemini-2.5-flash"
_MAX_TOKENS_DEBATE = 600
_MAX_TOKENS_GEMINI = 4000   # thinking model — 내부 추론 토큰 포함
_MAX_TOKENS_JUDGE = 500
_TIMEOUT = 30.0

_SYS_BULL = """한국어로만 작성. 한자·베트남어·일본어 금지(티커 영문 허용).
당신은 강세론자 애널리스트다. 이 종목의 성장·상승 논거를 evidence 수치 근거로 제시한다.
규칙:
- 직접 매수 권유 금지. "주목할 만함" 식 완곡 표현.
- 반드시 제공된 evidence 수치를 인용. 없는 데이터 추정 금지.
- 4~6문장으로 작성."""

_SYS_BEAR = """한국어로만 작성. 한자·베트남어·일본어 금지(티커 영문 허용).
당신은 약세론자 애널리스트다. 이 종목의 리스크·하락·과열 논거를 evidence 수치 근거로 제시한다.
규칙:
- 직접 매도 권유 금지. "유의 필요" 식 완곡 표현.
- 반드시 제공된 evidence 수치를 인용. 없는 데이터 추정 금지.
- 4~6문장으로 작성."""

_SYS_JUDGE = """한국어로만 작성. 한자·베트남어·일본어 금지(티커 영문 허용).
당신은 시니어 심판 애널리스트다. 강세론자와 약세론자의 2라운드 토론 전체를 읽고 종합 판정을 내린다.
반드시 아래 JSON 형식으로만 출력하라 (다른 텍스트 금지):
{"bull_score": <0-100>, "bear_score": <0-100>, "recommendation": "<주목할만함|중립|유의필요>", "verdict": "<3~5문장 종합 분석>"}
규칙:
- bull_score + bear_score 는 각각 독립 설득력 평가 (합이 100일 필요 없음).
- recommendation은 반드시 셋 중 하나: 주목할만함, 중립, 유의필요"""

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


async def _call_groq(messages: list[dict], max_tokens: int = _MAX_TOKENS_DEBATE) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY 없음")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _GROQ_URL,
            json={"model": _GROQ_MODEL, "max_tokens": max_tokens, "messages": messages},
            headers={"Authorization": f"Bearer {api_key}"},
        )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _call_gemini(messages: list[dict]) -> str:
    """Gemini 호출. GEMINI_API_KEY 미설정 시 Groq fallback. 429 시 60s 후 1회 재시도."""
    import asyncio as _asyncio
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("GEMINI_API_KEY 없음 — Groq fallback으로 약세 생성")
        return await _call_groq(messages)
    for attempt in range(2):
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _GEMINI_URL,
                json={"model": _GEMINI_MODEL, "max_tokens": _MAX_TOKENS_GEMINI, "messages": messages},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code == 429 and attempt == 0:
            log.warning("Gemini 429 rate limit — 60s 대기 후 재시도")
            await _asyncio.sleep(60)
            continue
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError("Gemini 429 재시도 실패")


def _parse_verdict(raw: str) -> dict:
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "bull_score": max(0, min(100, int(data.get("bull_score", 50)))),
                "bear_score": max(0, min(100, int(data.get("bear_score", 50)))),
                "recommendation": data.get("recommendation", "중립"),
                "text": _clean(data.get("verdict", "")),
            }
    except Exception:
        pass
    log.warning("verdict JSON 파싱 실패, 기본값 사용 (raw=%s)", raw[:100])
    return {"bull_score": 50, "bear_score": 50, "recommendation": "중립", "text": _clean(raw[:300])}


async def _run_debate(ticker: str, result: EngineResult) -> tuple[str, str]:
    session_id = str(uuid.uuid4())
    db.create_debate_session(session_id, ticker, result.total_score, result.signal)
    try:
        return await _run_debate_inner(session_id, ticker, result)
    except Exception:
        db.fail_debate_session(session_id)
        raise


async def _run_debate_inner(session_id: str, ticker: str, result: EngineResult) -> tuple[str, str]:

    user_prompt = _build_user_prompt(ticker, result)

    # Round 1: 강세(Groq) + 약세(Gemini) 동시 호출
    log.info("[%s] Round 1 시작", ticker)
    r1_bull, r1_bear = await asyncio.gather(
        _call_groq([{"role": "system", "content": _SYS_BULL}, {"role": "user", "content": user_prompt}]),
        _call_gemini([{"role": "system", "content": _SYS_BEAR}, {"role": "user", "content": user_prompt}]),
    )
    r1_bull, r1_bear = _clean(r1_bull), _clean(r1_bear)
    db.save_debate_round(session_id, 1, "groq", "gemini", r1_bull, r1_bear)
    log.info("[%s] Round 1 완료 (강세=%d자, 약세=%d자)", ticker, len(r1_bull), len(r1_bear))

    # Round 2: 상대 Round 1 읽고 재반박 동시 호출
    log.info("[%s] Round 2 시작", ticker)
    r2_bull, r2_bear = await asyncio.gather(
        _call_groq([
            {"role": "system", "content": _SYS_BULL},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": r1_bull},
            {"role": "user", "content": f"상대방 약세 주장:\n{r1_bear}\n\n위 약세 주장의 허점을 반박하고 강세 논거를 보완하라."},
        ]),
        _call_gemini([
            {"role": "system", "content": _SYS_BEAR},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": r1_bear},
            {"role": "user", "content": f"상대방 강세 주장:\n{r1_bull}\n\n위 강세 주장의 허점을 반박하고 약세 논거를 보완하라."},
        ]),
    )
    r2_bull, r2_bear = _clean(r2_bull), _clean(r2_bear)
    db.save_debate_round(session_id, 2, "groq", "gemini", r2_bull, r2_bear)
    log.info("[%s] Round 2 완료 (강세=%d자, 약세=%d자)", ticker, len(r2_bull), len(r2_bear))

    # Judge: 전체 4개 발언 종합 판정
    log.info("[%s] 심판 판정 시작", ticker)
    judge_prompt = (
        f"[강세 R1]\n{r1_bull}\n\n"
        f"[약세 R1]\n{r1_bear}\n\n"
        f"[강세 R2]\n{r2_bull}\n\n"
        f"[약세 R2]\n{r2_bear}"
    )
    verdict_raw = await _call_groq(
        [{"role": "system", "content": _SYS_JUDGE}, {"role": "user", "content": judge_prompt}],
        max_tokens=_MAX_TOKENS_JUDGE,
    )
    verdict = _parse_verdict(verdict_raw)
    db.save_debate_verdict(
        session_id, "groq",
        verdict["text"], verdict["bull_score"], verdict["bear_score"], verdict["recommendation"],
    )
    db.complete_debate_session(session_id)
    log.info(
        "[%s] 심판 판정 완료 (bull=%d, bear=%d, %s)",
        ticker, verdict["bull_score"], verdict["bear_score"], verdict["recommendation"],
    )

    return r2_bull, r2_bear


def generate_debate(ticker: str, result: EngineResult) -> tuple[str, str]:
    """Groq+Gemini 2라운드 토론 → (bull_text, bear_text). 실패 시 ("", "") 반환(graceful)."""
    try:
        return asyncio.run(_run_debate(ticker, result))
    except Exception as e:
        log.error("[%s] 토론 생성 실패: %s", ticker, e)
        return "", ""
