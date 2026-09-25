from pydantic import BaseModel, ConfigDict
from datetime import date
from app.models import EstadoReserva
from typing import Any

class HuespedBase(BaseModel):
    nombre: str
    telefono: str
    email: str

class HuespedCreate(HuespedBase):
    pass

class HuespedResponse(HuespedBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class ReservaBase(BaseModel):
    fecha_inicio: date
    fecha_fin: date
    huesped_id: int
    habitacion_id: int | None = None

class ReservaCreate(ReservaBase):
    pass

class ReservaResponse(ReservaBase):
    id: int
    estado: EstadoReserva
    habitacion_id: int | None = None
    model_config = ConfigDict(from_attributes=True)

class ErrorDetalle(BaseModel):
    tipo: str
    mensaje: str
    reserva_id: int | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetalle


class ErrorHTTPResponse(BaseModel):
    detail: str


class HabitacionDisponible(BaseModel):
    id: int
    numero: str
    tipo: str
    precio_noche: float

class DisponibilidadResponse(BaseModel):
    fecha_inicio: date
    fecha_fin: date
    total_disponibles: int
    habitaciones: list[HabitacionDisponible]

class ErrorValidacionDetalle(BaseModel):
    loc: list[str | int]
    msg: str
    type: str
    input: Any = None
    ctx: dict[str, Any] | None = None


class ErrorValidacionResponse(BaseModel):
    detail: list[ErrorValidacionDetalle]

class ResolucionEliminadaResponse(BaseModel):
    mensaje: str
    reserva_id: int
    accion: Literal["eliminada"]


class ResolucionCanceladaResponse(BaseModel):
    mensaje: str
    reserva: ReservaResponse
    accion: Literal["cancelada"]