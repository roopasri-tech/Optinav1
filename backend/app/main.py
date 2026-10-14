import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config.settings import settings
from app.database.session import SessionLocal
from app.routers import optimization, places, routes, vehicles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("smartroute")

app = FastAPI(
    title="SmartRoute API",
    description="Intelligent multi-fuel trip cost & stop optimisation for India "
                "(petrol, diesel, CNG, bi-fuel CNG+petrol, EV).",
    version="2.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(vehicles.router)
app.include_router(routes.router)
app.include_router(places.router)
app.include_router(optimization.router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    problems = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p not in ("body", "query", "path"))
        msg = err.get("msg", "invalid value").replace("Value error, ", "")
        problems.append(f"{loc}: {msg}" if loc else msg)
    return JSONResponse(status_code=422, content={"detail": "Invalid input - " + "; ".join(problems)})


@app.exception_handler(SQLAlchemyError)
async def db_error_handler(request: Request, exc: SQLAlchemyError):
    logger.error("Database error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "A database error occurred. Please try again."})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s", request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred. Please try again."})


@app.get("/api/health")
def health():
    db_ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return JSONResponse(status_code=200 if db_ok else 503,
                        content={"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unreachable",
                                 "service": "SmartRoute API"})


@app.get("/")
def root():
    return {"message": "SmartRoute API - see /docs for the Swagger UI"}
