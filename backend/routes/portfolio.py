"""Portfolio routes: upload CSV/XLSX/XLS, list positions, summary."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.schemas import PortfolioSummary, PositionOut, UploadOut
from core.portfolio_engine import compute_positions, portfolio_summary
from db.repositories import holdings_repo
from services.portfolio_loader import (
    SUPPORTED_EXTENSIONS,
    UnmappedSymbolError,
    parse_portfolio_file,
)

router = APIRouter()


@router.post("/upload", response_model=UploadOut)
async def upload(file: UploadFile = File(...)) -> UploadOut:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)
    try:
        parsed = parse_portfolio_file(tmp_path)
    except UnmappedSymbolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    for h in parsed:
        holdings_repo.upsert_stock(h.symbol, h.name, asset_type=h.asset_type)
    n = holdings_repo.replace_holdings(
        [(h.symbol, h.quantity, h.avg_cost, h.asset_type) for h in parsed]
    )
    return UploadOut(holdings_loaded=n)


@router.get("/positions", response_model=list[PositionOut])
def positions() -> list[PositionOut]:
    try:
        return [PositionOut(**p.as_dict()) for p in compute_positions()]
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/summary", response_model=PortfolioSummary)
def summary() -> PortfolioSummary:
    try:
        return PortfolioSummary(**portfolio_summary())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
