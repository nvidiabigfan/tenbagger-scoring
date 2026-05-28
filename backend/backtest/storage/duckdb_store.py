"""DuckDB 웨어하우스 접근 레이어.

운영 Supabase와 완전 분리된 백테스트 전용 OLAP 저장소.
파일 위치: backend/backtest/data/warehouse.duckdb (gitignore)
"""

from __future__ import annotations

from pathlib import Path

import duckdb

_DEFAULT_PATH = Path(__file__).parent.parent / "data" / "warehouse.duckdb"
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(
    db_path: Path | str | None = None,
    memory_limit: str = "1GB",
) -> duckdb.DuckDBPyConnection:
    """DuckDB 연결 반환. 최초 호출 시 schema 자동 적용."""
    path = Path(db_path) if db_path else _DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    # 2.8M rows × window functions → 메모리 제한 + 디스크 spill 허용
    tmp_dir = path.parent / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute(f"SET temp_directory='{tmp_dir}'")
    _apply_schema(con)
    return con


def _apply_schema(con: duckdb.DuckDBPyConnection) -> None:
    """CREATE TABLE IF NOT EXISTS 이므로 매번 호출해도 안전."""
    schema_sql = _SCHEMA_PATH.read_text()
    con.execute(schema_sql)
