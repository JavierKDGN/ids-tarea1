import os
from datetime import date
from typing import List
from contextlib import asynccontextmanager
from secrets import compare_digest

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.error_models import *
from app.database import engine, Base, get_db
from app.grpc import get_habitaciones_client, GrpcHabitacionesClient
from app import models, schema, crud, services, error_dicts


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.getenv("API_KEY"):
        raise RuntimeError("API_KEY debe estar configurada")
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="Sistema de Reservas - Cadena Hotelera Costanera",
    version="1.0.0",
    description="API REST pública (v1) para gestión de huéspedes y reservas, integrada internamente vía gRPC con el Sistema de Habitaciones.",
    lifespan=lifespan
)

# Autenticacion

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str | None = Depends(api_key_header)) -> None:
    esperada = os.environ.get("API_KEY", "")
    if not api_key or not esperada or not compare_digest(api_key.encode(), esperada.encode()):
        raise HTTPException(
            status_code=401,
            detail="API Key ausente o inválida",
            headers={"WWW-Authenticate": "APIKey"},
        )

# Manejo de errores

@app.exception_handler(ErrorReserva)
async def manejar_error_reserva(request: Request, exc: ErrorReserva) -> JSONResponse:
    if isinstance(exc, DatosInvalidos):
        status = 422
        mensaje = str(exc)
    elif isinstance(exc, HuespedNoExiste):
        status = 404
        mensaje = f"No existe el huesped {exc}"
    elif isinstance(exc, ReservaNoExiste):
        status = 404
        mensaje = f"No existe la reserva {exc}"
    elif isinstance(exc, (EstadoInvalido, SinDisponibilidad)):
        status = 409
        mensaje = str(exc)
    elif isinstance(exc, ReservaIncierta):
        status = 503
        mensaje = str(exc)
    else:
        status = 500
        mensaje = "No se pudo completar la operacion"

    detalle: dict[str, str | int] = {
        "tipo": type(exc).__name__,
        "mensaje": mensaje
    }
    if isinstance(exc, ReservaIncierta):
        detalle["reserva_id"] = exc.reserva_id
    return JSONResponse(status_code=status, content={"error": detalle})

@app.exception_handler(ConnectionError)
@app.exception_handler(TimeoutError)
async def manejar_error_habitaciones(
    request: Request, exc: Exception
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "tipo": "HabitacionesNoDisponible",
                "mensaje": "No fue posible comunicarse con Habitaciones",
            }
        },
    )

@app.exception_handler(SQLAlchemyError)
async def manejar_error_bd(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {
            "tipo": "BaseDeDatosNoDisponible",
            "mensaje": "No se pudo completar la operacion"
        }},
    )

# Healthcheck endpoint

@app.get("/", tags=["Salud"])
def health_check():
    return {
        "sistema": "API de Reservas - Cadena Hotelera Costanera",
        "version": "v1",
        "docs": "/docs",
        "estado": "operativo"
    }


# ==========================================
# Endpoints de Huéspedes (/v1/huespedes)
# ==========================================
@app.post(
    "/v1/huespedes",
    response_model=schema.HuespedResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Huéspedes"],
    dependencies=[Depends(verify_api_key)],
    responses={
        **error_dicts.RESPUESTAS_BD,
        409: {
            "model": schema.ErrorHTTPResponse,
            "description": "Ya existe un huesped con ese correo",
        }
    }
)
def registrar_huesped(
    huesped_in: schema.HuespedCreate,
    db: Session = Depends(get_db)
):
    huesped_crud = crud.HuespedCRUD(db)
    creado = huesped_crud.create_huesped(huesped_in)
    if creado is None:
        raise HTTPException(
            status_code=409,
            detail="Ya existe un huesped con ese correo"
        )
    return creado


@app.get(
    "/v1/huespedes",
    response_model=List[schema.HuespedResponse],
    tags=["Huéspedes"],
    dependencies=[Depends(verify_api_key)],
    responses=error_dicts.RESPUESTAS_BD,
)
def listar_huespedes(db: Session = Depends(get_db)):
    return crud.HuespedCRUD(db).get_huespedes()


@app.get(
    "/v1/huespedes/{huesped_id}",
    response_model=schema.HuespedResponse,
    tags=["Huéspedes"],
    dependencies=[Depends(verify_api_key)],
    responses={
        **error_dicts.RESPUESTAS_BD,
        404: {
            "model": schema.ErrorResponse,
            "description": "El huésped solicitado no existe",
        }
    }
)

def consultar_huesped(huesped_id: int, db: Session = Depends(get_db)):
    huesped = crud.HuespedCRUD(db).get_huesped(huesped_id)
    if huesped is None:
        raise HuespedNoExiste(huesped_id)
    return huesped


# ==========================================
# Endpoints de Reservas (/v1/reservas)
# ==========================================
@app.post(
    "/v1/reservas",
    response_model=schema.ReservaResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Reservas"],
    dependencies=[Depends(verify_api_key)],
    summary="Crear una reserva",
    description=(
        "Registra una reserva pendiente y solicita la asignación a "
        "Habitaciones por gRPC. Devuelve 201 al confirmar. "
        "Si no hay disponibilidad, intenta eliminar el registro pendiente "
        "y devuelve 409. Ante un resultado incierto, intenta marcar la "
        "reserva para reparación y devuelve 503. "
        "Las fechas representan el intervalo [fecha_inicio, fecha_fin). "
        "Si habitacion_id se omite o es null, se solicita asignación automática. "
        "Este POST no implementa Idempotency-Key."
    ),
    responses={
        401: error_dicts.ERROR_401,
        404: {
            "model": schema.ErrorResponse,
            "description": "El huésped no existe",
        },
        409: {
            "model": schema.ErrorResponse,
            "description": "No hay habitación disponible para la estadía",
        },
        422: error_dicts.ERROR_DATOS_422,
        503: error_dicts.ERROR_OPERACION_503
    },
)
def crear_reserva(
    reserva_in: schema.ReservaCreate,
    db: Session = Depends(get_db),
    habitaciones: GrpcHabitacionesClient = Depends(get_habitaciones_client)
):
    return services.crear_reserva(db, reserva_in, habitaciones)

@app.get(
    "/v1/reservas",
    response_model=List[schema.ReservaResponse],
    tags=["Reservas"],
    dependencies=[Depends(verify_api_key)],
    responses=error_dicts.RESPUESTAS_BD
)
def listar_reservas(db: Session = Depends(get_db)):
    return crud.ReservaCRUD(db).get_reservas()

@app.get(
    "/v1/reservas/{reserva_id}",
    response_model=schema.ReservaResponse,
    tags=["Reservas"],
    dependencies=[Depends(verify_api_key)],
    responses={
        **error_dicts.RESPUESTAS_BD,
        404: error_dicts.ERROR_RESERVA_404
    }
)
def consultar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    reserva = crud.ReservaCRUD(db).get_reserva_by_id(reserva_id)
    if reserva is None:
        raise ReservaNoExiste(reserva_id)
    return reserva


@app.delete(
    "/v1/reservas/{reserva_id}",
    response_model=schema.ReservaResponse,
    tags=["Reservas"],
    summary="Cancelar una reserva",
    description=(
        "Cancela una reserva confirmada y libera su asignación mediante gRPC. "
        "Conserva el registro local. Si la reserva ya está cancelada, "
        "devuelve 200 sin repetir la liberación. Otros estados producen 409."
    ),
    dependencies=[Depends(verify_api_key)],
    responses={
        401: error_dicts.ERROR_401,
        404: error_dicts.ERROR_RESERVA_404,
        409: error_dicts.ERROR_ESTADO_409,
        503: error_dicts.ERROR_OPERACION_503
    }
)
def cancelar_reserva(
    reserva_id: int,
    db: Session = Depends(get_db),
    habitaciones: GrpcHabitacionesClient = Depends(get_habitaciones_client)
):
    """Revertir / cancelar una estadía y liberar la habitación en Habitaciones vía gRPC."""
    return services.cancelar_reserva(db, reserva_id, habitaciones)

@app.post(
    "/v1/reservas/{reserva_id}/resolver",
    tags=["Reservas"],
    summary="Resolver una reserva en pendiente o incierta",
    description=(
        "Consulta la asignación remota y la libera si corresponde. "
        "Si la reserva local no tiene habitacion_id, elimina el registro; "
        "si tiene habitacion_id, termina en estado cancelada. "
        "Una reserva confirmada produce 409. Una reserva ya cancelada "
        "se devuelve sin cambios con accion cancelada."
    ),
    dependencies=[Depends(verify_api_key)],
    responses={
        401: error_dicts.ERROR_401,
        404: error_dicts.ERROR_RESERVA_404,
        409: error_dicts.ERROR_ESTADO_409,
        503: error_dicts.ERROR_OPERACION_503
    }
)
def resolver_reserva_en_reparacion(
    reserva_id: int,
    db: Session = Depends(get_db),
    habitaciones: GrpcHabitacionesClient = Depends(get_habitaciones_client)
):
    """
    Resuelve una reserva en estado 'reparacion' (Saga Compensation / Rollback Cascade).
    Verifica con Habitaciones vía gRPC si la habitación quedó asignada y, de ser así,
    la libera para evitar bloqueos huérfanos, revirtiendo la reserva local.
    """
    resultado = services.resolver_reserva(db, reserva_id, habitaciones)
    if resultado is None:
        return {
            "mensaje": f"Reserva {reserva_id} resuelta: el registro local fue eliminado",
            "reserva_id": reserva_id,
            "accion": "eliminada"
        }
    return {
        "mensaje": f"Reserva {reserva_id} resuelta: reserva cancelada",
        "reserva": resultado,
        "accion": "cancelada"
    }



# ==========================================
# Endpoint de Disponibilidad (/v1/disponibilidad)
# ==========================================
@app.get(
    "/v1/disponibilidad",
    tags=["Disponibilidad"],
    summary="Consultar disponibilidad",
    description=(
        "Consulta Habitaciones por gRPC para el intervalo "
        "[fecha_inicio, fecha_fin). La salida debe ser posterior "
        "a la entrada. Esta consulta no reserva habitaciones. "
        "Si no hay disponibilidad, devuelve 200 con una lista vacía."
    ),
    response_model=schema.DisponibilidadResponse,
    dependencies=[Depends(verify_api_key)],
    responses={
        401: error_dicts.ERROR_401,
        422: error_dicts.ERROR_DATOS_422,
        503: {
            "model": schema.ErrorResponse,
            "description": "No fue posible comunicarse con Habitaciones.",
        },
    }
)
def consultar_disponibilidad(
    fecha_inicio: date = Query(..., description="Fecha de check-in (YYYY-MM-DD)"),
    fecha_fin: date = Query(..., description="Fecha de check-out (YYYY-MM-DD)"),
    habitaciones: GrpcHabitacionesClient = Depends(get_habitaciones_client)
):
    if fecha_fin <= fecha_inicio:
        raise DatosInvalidos("La fecha de salida debe ser posterior a la de entrada")
    libres = habitaciones.consultar_disponibilidad(fecha_inicio, fecha_fin)
    return {
        "fecha_inicio": fecha_inicio.isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "total_disponibles": len(libres),
        "habitaciones": [
            {
                "id": h.id,
                "numero": h.numero,
                "tipo": h.tipo,
                "precio_noche": h.precio_noche
            }
            for h in libres
        ]
    }

