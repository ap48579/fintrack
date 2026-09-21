from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import alerts, assistant, hypotheses, push, research, signals, stock, verdicts, watchlist, whales

app = FastAPI(title="FinTrack API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stock.router)
app.include_router(watchlist.router)
app.include_router(whales.router)
app.include_router(signals.router)
app.include_router(research.router)
app.include_router(alerts.router)
app.include_router(push.router)
app.include_router(verdicts.router)
app.include_router(assistant.router)
app.include_router(hypotheses.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
