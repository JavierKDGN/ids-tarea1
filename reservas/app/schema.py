from pydantic import BaseModel, ConfigDict
from datetime import date
from app.models import EstadoReserva

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
