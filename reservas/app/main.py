import os
from contextlib import asynccontextmanager
from secrets import compare_digest

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models  
from .crud import HuespedCRUD, ReservaCRUD
from .database import Base, engine, get_db
from .errors import *
from .grpc import MockHabitacion
from .schema import HuespedCreate, HuespedResponse, ReservaCreate, ReservaResponse
from .services import cancelar_reserva, crear_reserva, resolver_reserva


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("RESERVAS_API_KEY"):
        raise RuntimeError("RESERVAS_API_KEY debe estar configurada")
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="API de Reservas", version="1.0.0", lifespan=lifespan)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
habitaciones = MockHabitacion()


def verificar_api_key(api_key: str | None = Depends(api_key_header)) -> None:
    esperada = os.environ.get("RESERVAS_API_KEY", "")
    if not api_key or not esperada or not compare_digest(api_key.encode(), esperada.encode()):
        raise HTTPException(
            status_code=401,
            detail="API Key ausente o inválida",
            headers={"WWW-Authenticate": "APIKey"},
        )


def get_habitaciones() -> MockHabitacion:
    return habitaciones


@app.exception_handler(ErrorReserva)
async def manejar_error_reserva(request: Request, exc: ErrorReserva) -> JSONResponse:
    if isinstance(exc, DatosInvalidos):
        status = 422
    elif isinstance(exc, (HuespedNoExiste, ReservaNoExiste)):
        status = 404
    elif isinstance(exc, (EstadoInvalido, SinDisponibilidad)):
        status = 409
    elif isinstance(exc, ReservaIncierta):
        status = 503
    else:
        status = 500

    detalle: dict[str, str | int] = {"tipo": type(exc).__name__, "mensaje": str(exc)}
    if isinstance(exc, ReservaIncierta):
        detalle["reserva_id"] = exc.reserva_id
    return JSONResponse(status_code=status, content={"error": detalle})


@app.exception_handler(SQLAlchemyError)
async def manejar_error_bd(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"tipo": "BaseDeDatosNoDisponible", "mensaje": "No se pudo completar la operacion"}},
    )


router = APIRouter(prefix="/v1", dependencies=[Depends(verificar_api_key)])


@router.post("/huespedes", response_model=HuespedResponse, status_code=201, tags=["Huespedes"])
def registrar_huesped(datos: HuespedCreate, db: Session = Depends(get_db)):
    huesped = HuespedCRUD(db).create_huesped(datos)
    if huesped is None:
        raise HTTPException(status_code=409, detail="Ya existe un huesped con ese correo")
    return huesped


@router.get("/huespedes", response_model=list[HuespedResponse], tags=["Huespedes"])
def listar_huespedes(db: Session = Depends(get_db)):
    return HuespedCRUD(db).get_huespedes()


@router.get("/huespedes/{huesped_id}", response_model=HuespedResponse, tags=["Huespedes"])
def consultar_huesped(huesped_id: int, db: Session = Depends(get_db)):
    huesped = HuespedCRUD(db).get_huesped(huesped_id)
    if huesped is None:
        raise HuespedNoExiste(f"No existe el huesped {huesped_id}")
    return huesped


@router.post("/reservas", response_model=ReservaResponse, status_code=201, tags=["Reservas"])
def registrar_reserva(
    datos: ReservaCreate,
    db: Session = Depends(get_db),
    habitaciones_cliente: MockHabitacion = Depends(get_habitaciones),
):
    return crear_reserva(db, datos, habitaciones_cliente)


@router.get("/reservas", response_model=list[ReservaResponse], tags=["Reservas"])
def listar_reservas(db: Session = Depends(get_db)):
    return ReservaCRUD(db).get_reservas()


@router.get("/reservas/{reserva_id}", response_model=ReservaResponse, tags=["Reservas"])
def consultar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    reserva = ReservaCRUD(db).get_reserva_by_id(reserva_id)
    if reserva is None:
        raise ReservaNoExiste(f"No existe la reserva {reserva_id}")
    return reserva


@router.delete("/reservas/{reserva_id}", response_model=ReservaResponse, tags=["Reservas"])
def anular_reserva(
    reserva_id: int,
    db: Session = Depends(get_db),
    habitaciones_cliente: MockHabitacion = Depends(get_habitaciones),
):
    return cancelar_reserva(db, reserva_id, habitaciones_cliente)


@router.post(
    "/reservas/{reserva_id}/reconciliar",
    response_model=ReservaResponse,
    responses={204: {"description": "Reserva pendiente retirada tras la reconciliación"}},
    tags=["Reservas"],
)
def reconciliar_reserva(
    reserva_id: int,
    db: Session = Depends(get_db),
    habitaciones_cliente: MockHabitacion = Depends(get_habitaciones),
):
    resultado = resolver_reserva(db, reserva_id, habitaciones_cliente)
    if resultado is None:
        return Response(status_code=204)
    return resultado


app.include_router(router)


@app.get("/", include_in_schema=False)
def read_root():
    return {"servicio": "reservas", "version": "v1"}
