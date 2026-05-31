from dotenv import load_dotenv

load_dotenv()

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.analyze import router as analyze_router
from app.routes.supply import router as supply_router

app = FastAPI(title="텐배거스코어링 API", version="0.1.0")

_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
_origins = ["*"] if _origins_env == "*" else [o.strip() for o in _origins_env.split(",")]

# allow_origins=["*"] 와 allow_credentials=True 조합은 CORS spec 위반 —
# wildcard 시 credentials 비활성화, 명시된 origin 목록일 때만 credentials 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=(_origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(supply_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
