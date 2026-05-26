"""Resend 이메일 발송 유틸."""
import logging
import os

import httpx

log = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_FRONTEND_URL = os.getenv(
    "FRONTEND_URL", "https://frontend-phi-seven-pkbkixbxfa.vercel.app"
)


def send_score_alert(
    to: str,
    ticker: str,
    old_score: float,
    new_score: float,
) -> bool:
    """점수 변화 알림 이메일. RESEND_API_KEY 미설정 시 False 반환."""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        log.warning("RESEND_API_KEY 미설정 — 이메일 스킵 (%s)", ticker)
        return False

    delta = new_score - old_score
    direction = "상승 ▲" if delta > 0 else "하락 ▼"
    from_addr = os.getenv("RESEND_FROM", "alerts@tenbagger.resend.dev")

    html = f"""
<div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px">
  <h2 style="color:#1e293b;margin-bottom:4px">텐배거 스코어 알림</h2>
  <p style="color:#64748b;margin-top:0">{ticker} 스코어 변동</p>
  <div style="background:#f8fafc;border-radius:12px;padding:20px;margin:16px 0;text-align:center">
    <div style="font-size:14px;color:#64748b">이전 → 현재</div>
    <div style="font-size:36px;font-weight:800;color:#0f172a;margin:8px 0">
      {old_score:.0f} → {new_score:.0f}
    </div>
    <div style="font-size:16px;color:{'#16a34a' if delta > 0 else '#dc2626'};font-weight:600">
      {direction} {abs(delta):.1f}점
    </div>
  </div>
  <a href="{_FRONTEND_URL}/analyze/{ticker}"
     style="display:block;background:#2563eb;color:#fff;text-align:center;
            padding:12px;border-radius:8px;text-decoration:none;font-weight:600">
    분석 결과 보기 →
  </a>
  <p style="color:#94a3b8;font-size:11px;margin-top:20px;text-align:center">
    본 서비스는 투자 자문이 아니며 참고용입니다.<br>
    알림을 끄려면 워치리스트 설정에서 해제하세요.
  </p>
</div>
"""

    try:
        r = httpx.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": from_addr,
                "to": [to],
                "subject": f"[텐배거] {ticker} 스코어 {direction} ({old_score:.0f} → {new_score:.0f})",
                "html": html,
            },
            timeout=10,
        )
        r.raise_for_status()
        log.info("이메일 발송 완료: %s → %s", ticker, to)
        return True
    except Exception as e:
        log.error("이메일 발송 실패 (%s → %s): %s", ticker, to, e)
        return False
