import os
from datetime import date
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Security, Query
from fastapi.security import APIKeyHeader
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db
from app import models, schema, crud, services
from app.errors import (
    ErrorReserva,
    DatosInvalidos,
    HuespedNoExiste,
    ReservaNoExiste,
    EstadoInvalido,
    SinDisponibilidad,
    ReservaIncierta
)
from app.grpc import get_habitaciones_client, GrpcHabitacionesClient

# Crear tablas en PostgreSQL si no existen
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Error al inicializar tablas en PostgreSQL: {e}")

app = FastAPI(
    title="Sistema de Reservas - Cadena Hotelera Costanera",
    version="1.0.0",
    description="API REST pública (v1) para gestión de huéspedes y reservas, integrada internamente vía gRPC con el Sistema de Habitaciones."
)

# ==========================================
# Seguridad y Autenticación (Requisito T6)
# ==========================================
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="API Key para autorización de endpoints /v1")


def verify_api_key(api_key: Optional[str] = Security(api_key_header)):
    expected_key = os.getenv("API_KEY", "hotel-secret-key-2026")
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Unauthorized", "message": "API Key inválida o no proporcionada en la cabecera X-API-Key"}
        )
    return api_key


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
    dependencies=[Depends(verify_api_key)]
)
def registrar_huesped(
    huesped_in: schema.HuespedCreate,
    db: Session = Depends(get_db)
):
    huesped_crud = crud.HuespedCRUD(db)
    if huesped_crud.get_huesped_by_email(huesped_in.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Conflict", "message": f"Ya existe un huésped registrado con el correo {huesped_in.email}"}
        )

    creado = huesped_crud.create_huesped(huesped_in)
    if not creado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Bad Request", "message": "No fue posible registrar el huésped"}
        )
    return creado


@app.get(
    "/v1/huespedes",
    response_model=List[schema.HuespedResponse],
    tags=["Huéspedes"],
    dependencies=[Depends(verify_api_key)]
)
def listar_huespedes(db: Session = Depends(get_db)):
    return crud.HuespedCRUD(db).get_huespedes()


@app.get(
    "/v1/huespedes/{huesped_id}",
    response_model=schema.HuespedResponse,
    tags=["Huéspedes"],
    dependencies=[Depends(verify_api_key)]
)
def consultar_huesped(huesped_id: int, db: Session = Depends(get_db)):
    huesped = crud.HuespedCRUD(db).get_huesped(huesped_id)
    if not huesped:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Not Found", "message": f"Huésped con ID {huesped_id} no encontrado"}
        )
    return huesped


# ==========================================
# Endpoints de Reservas (/v1/reservas)
# ==========================================
@app.post(
    "/v1/reservas",
    response_model=schema.ReservaResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Reservas"],
    dependencies=[Depends(verify_api_key)]
)
def crear_reserva(
    reserva_in: schema.ReservaCreate,
    db: Session = Depends(get_db),
    habitaciones: GrpcHabitacionesClient = Depends(get_habitaciones_client)
):
    try:
        return services.crear_reserva(db, reserva_in, habitaciones)
    except DatosInvalidos as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Bad Request", "message": str(e)}
        )
    except HuespedNoExiste as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Not Found", "message": f"Huésped con ID {e} no existe"}
        )
    except SinDisponibilidad as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "Conflict", "message": str(e)}
        )
    except (ReservaIncierta, ConnectionError, TimeoutError) as e:
        # Requisito T7: Manejo de fallas de dependencia (503 Service Unavailable)
        reserva_id = getattr(e, "reserva_id", None)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Service Unavailable",
                "message": "El servicio de Habitaciones (gRPC) no responde. La solicitud no pudo confirmarse y se marcó para reparación.",
                "reserva_id": reserva_id
            }
        )


@app.get(
    "/v1/reservas",
    response_model=List[schema.ReservaResponse],
    tags=["Reservas"],
    dependencies=[Depends(verify_api_key)]
)
def listar_reservas(db: Session = Depends(get_db)):
    return crud.ReservaCRUD(db).get_reservas()


@app.get(
    "/v1/reservas/{reserva_id}",
    response_model=schema.ReservaResponse,
    tags=["Reservas"],
    dependencies=[Depends(verify_api_key)]
)
def consultar_reserva(reserva_id: int, db: Session = Depends(get_db)):
    reserva = crud.ReservaCRUD(db).get_reserva_by_id(reserva_id)
    if not reserva:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Not Found", "message": f"Reserva con ID {reserva_id} no encontrada"}
        )
    return reserva


@app.delete(
    "/v1/reservas/{reserva_id}",
    response_model=schema.ReservaResponse,
    tags=["Reservas"],
    dependencies=[Depends(verify_api_key)]
)
def cancelar_reserva(
    reserva_id: int,
    db: Session = Depends(get_db),
    habitaciones: GrpcHabitacionesClient = Depends(get_habitaciones_client)
):
    """Revertir / cancelar una estadía y liberar la habitación en Habitaciones vía gRPC."""
    try:
        return services.cancelar_reserva(db, reserva_id, habitaciones)
    except ReservaNoExiste as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Not Found", "message": f"Reserva con ID {reserva_id} no encontrada"}
        )
    except EstadoInvalido as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Bad Request", "message": str(e)}
        )
    except (ReservaIncierta, ConnectionError, TimeoutError) as e:
        # Requisito T7
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Service Unavailable",
                "message": "Falla al comunicar con el servicio de Habitaciones para liberar la estadía.",
                "reserva_id": reserva_id
            }
        )


@app.post(
    "/v1/reservas/{reserva_id}/resolver",
    tags=["Reservas"],
    dependencies=[Depends(verify_api_key)]
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
    try:
        resultado = services.resolver_reserva(db, reserva_id, habitaciones)
        if resultado is None:
            return {
                "mensaje": f"Reserva {reserva_id} resuelta con éxito: no hubo asignación en Habitaciones y fue limpiada del sistema.",
                "reserva_id": reserva_id,
                "accion": "eliminada"
            }
        return {
            "mensaje": f"Reserva {reserva_id} resuelta con éxito: se liberó la habitación en Habitaciones y se canceló la reserva.",
            "reserva": resultado,
            "accion": "cancelada"
        }
    except ReservaNoExiste:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Not Found", "message": f"Reserva con ID {reserva_id} no encontrada"}
        )
    except (ReservaIncierta, ConnectionError, TimeoutError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Service Unavailable", "message": "Aún no es posible conectar con Habitaciones para resolver la reserva."}
        )



# ==========================================
# Endpoint de Disponibilidad (/v1/disponibilidad)
# ==========================================
@app.get(
    "/v1/disponibilidad",
    tags=["Disponibilidad"],
    dependencies=[Depends(verify_api_key)]
)
def consultar_disponibilidad(
    fecha_inicio: date = Query(..., description="Fecha de check-in (YYYY-MM-DD)"),
    fecha_fin: date = Query(..., description="Fecha de check-out (YYYY-MM-DD)"),
    habitaciones: GrpcHabitacionesClient = Depends(get_habitaciones_client)
):
    if fecha_fin <= fecha_inicio:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Bad Request", "message": "La fecha de fin debe ser posterior a la de inicio"}
        )
    try:
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
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Service Unavailable", "message": "No fue posible consultar disponibilidad en Habitaciones"}
        )
