import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analyzers.analyst import AnalystAnalyzer
from app.analyzers.etf import EtfAnalyzer
from app.analyzers.trends import TrendsAnalyzer
from app.analyzers.youtube import YouTubeAnalyzer
from app.db import client as db
from app.scoring.engine import ScoringEngine

router = APIRouter(prefix="/analyze", tags=["analyze"])

_engine: ScoringEngine | None = None


def _get_engine() -> ScoringEngine:
    global _engine
    if _engine is None:
        _engine = ScoringEngine([EtfAnalyzer(), AnalystAnalyzer(), TrendsAnalyzer(), YouTubeAnalyzer()])
    return _engine


def _valid_ticker(ticker: str) -> bool:
    if not (1 <= len(ticker) <= 5):
        return False
    if ticker.count(".") > 1:
        return False
    return bool(re.fullmatch(r"[A-Z]+(\.[A-Z]+)?", ticker))


class ModuleResult(BaseModel):
    score: float
    signal: str
    confidence: float
    evidence: dict


class AnalyzeResponse(BaseModel):
    ticker: str
    total_score: float
    signal: str
    confidence: float
    report_md: str
    analyzed_at: str
    from_cache: bool
    analysis_id: str
    modules: dict[str, ModuleResult]


@router.post("/{ticker}", response_model=AnalyzeResponse)
def analyze(ticker: str):
    ticker = ticker.upper().strip()
    if not _valid_ticker(ticker):
        raise HTTPException(
            status_code=422,
            detail="티커 형식 오류: A-Z + 점 1개 이내, 5자 이하",
        )

    # 24시간 캐시
    cached = db.get_recent_analysis(ticker)
    if cached:
        modules = {
            m["module_name"]: ModuleResult(
                score=float(m["score"]),
                signal=m["signal"],
                confidence=float(m["confidence"]),
                evidence=m["evidence"] or {},
            )
            for m in cached.get("module_scores", [])
        }
        return AnalyzeResponse(
            ticker=cached["ticker"],
            total_score=float(cached["total_score"]),
            signal=cached["signal"],
            confidence=float(cached["confidence"]),
            report_md=cached["report_md"],
            analyzed_at=cached["analyzed_at"],
            from_cache=True,
            analysis_id=cached["id"],
            modules=modules,
        )

    # 신규 분석
    result = _get_engine().analyze(ticker)

    try:
        analysis_id, analyzed_at, report_md = db.save_analysis(result)
    except Exception as exc:
        # DB 저장 실패해도 분석 결과 반환
        analysis_id = "unsaved"
        analyzed_at = datetime.now(timezone.utc).isoformat()
        report_md = f"저장 오류: {exc}"

    return AnalyzeResponse(
        ticker=result.ticker,
        total_score=result.total_score,
        signal=result.signal,
        confidence=result.confidence,
        report_md=report_md,
        analyzed_at=analyzed_at,
        from_cache=False,
        analysis_id=analysis_id,
        modules={
            name: ModuleResult(
                score=r.score,
                signal=r.signal,
                confidence=r.confidence,
                evidence=r.evidence,
            )
            for name, r in result.module_results.items()
        },
    )
