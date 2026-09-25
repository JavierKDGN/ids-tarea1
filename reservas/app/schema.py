from pydantic import BaseModel, ConfigDict, computed_field
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

#computed_field pues _link no necesita ser guardado en la bd
class ReservaResponse(ReservaBase):
    id: int
    estado: EstadoReserva
    habitacion_id: int | None = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field(alias="_links", repr=False)
    @property
    def links(self) -> dict[str, dict[str, str]]:
        """Enlaces de acciones disponibles según el estado de la reserva."""
        base = f"/v1/reservas/{self.id}"

        links = {
            "self": {
                "href": base,
                "method": "GET"
            }
        }

        if self.estado == EstadoReserva.CONFIRMADA:
            links["cancelar"] = {
                "href": base,
                "method": "DELETE"
            }

        elif self.estado == EstadoReserva.REPARACION:
            links["resolver"] = {
                "href": f"{base}/resolver",
                "method": "POST"
            }

        return links