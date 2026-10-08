"""HTTP entry point for the fintech media indexing example."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from fintech_media_index import (
    FintechMediaIndexer,
    IndexRecord,
    IndexRequest,
    InfraiClient,
    InfraiError,
    TransportError,
)


app = FastAPI(title="Fintech media metadata index")


def build_indexer() -> FintechMediaIndexer:
    bucket = os.environ.get("MEDIA_BUCKET", "fintech-media-library")
    return FintechMediaIndexer(InfraiClient(), bucket)


@app.exception_handler(InfraiError)
async def handle_infrai_error(_request: object, error: InfraiError) -> JSONResponse:
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return JSONResponse(
        status_code=status,
        content={"error": {"code": error.code, "detail": error.detail}},
    )


@app.exception_handler(TransportError)
async def handle_transport_error(_request: object, error: TransportError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": {"message": str(error)}})


@app.post("/index", response_model=IndexRecord)
def index_asset(request: IndexRequest) -> IndexRecord:
    indexer = build_indexer()
    library = indexer.prepare_library()
    try:
        return indexer.index(request, library)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
