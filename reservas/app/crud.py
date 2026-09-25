from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from datetime import date

from .models import Huesped, Reserva, EstadoReserva
from .schema import HuespedCreate, HuespedResponse, ReservaCreate, ReservaResponse

class HuespedCRUD:
    def __init__(self, db: Session):
        self.db = db

    def create_huesped(self, huesped: HuespedCreate):
        new_huesped = Huesped(
            **huesped.model_dump()
        )

        try:
            self.db.add(new_huesped)
            self.db.commit()
            self.db.refresh(new_huesped)
            return HuespedResponse.model_validate(new_huesped)
        
        except IntegrityError:
            self.db.rollback()
            return None

    def get_huesped(self, huesped_id: int):
        return self.db.get(Huesped, huesped_id)

    def get_huespedes(self):
        huespedes = select(Huesped)
        return self.db.scalars(huespedes).all()

    def get_huesped_by_email(self, email: str):
        query = select(Huesped).where(Huesped.email == email)
        return self.db.scalars(query).first()

    def delete_huesped_by_id(self, huesped_id: int):
        huesped = self.get_huesped(huesped_id)
        if huesped:
            self.db.delete(huesped)
            self.db.commit()
            return True
        return False

class ReservaCRUD:
    def __init__(self, db: Session):
        self.db = db

    def _guardar(self, reserva: Reserva) -> ReservaResponse:
        try:
            self.db.commit()
            self.db.refresh(reserva)
        except SQLAlchemyError:
            self.db.rollback()
            raise

        return ReservaResponse.model_validate(reserva)

    def create_reserva(self, reserva: ReservaCreate, idempotency_key: str | None = None):
        datos = reserva.model_dump()
        datos.pop("habitacion_id", None)
        new_reserva = Reserva(
            **datos,
            estado=EstadoReserva.PENDIENTE,
            habitacion_id=None,
            idempotency_key=idempotency_key
        )
        self.db.add(new_reserva)
        return self._guardar(new_reserva)

    def get_reserva_by_id(self, reserva_id: int) -> Reserva | None:
        return self.db.get(Reserva, reserva_id)

    def get_reservas(self):
        reservas = select(Reserva)
        return self.db.scalars(reservas).all()

    def confirmar_reserva(self, reserva_id: int, habitacion_id: int) -> ReservaResponse | None:
        reserva = self.get_reserva_by_id(reserva_id)
        if reserva is None:
            return None

        reserva.habitacion_id = habitacion_id
        reserva.estado = EstadoReserva.CONFIRMADA
        return self._guardar(reserva)

    def cambiar_estado_reserva(self, reserva_id: int, nuevo_estado: EstadoReserva) -> ReservaResponse | None:
        reserva = self.get_reserva_by_id(reserva_id)
        if reserva is None:
            return None

        reserva.estado = nuevo_estado
        return self._guardar(reserva)
        
    def delete_reserva_by_id(self, reserva_id: int) -> bool:
        reserva = self.get_reserva_by_id(reserva_id)
        if reserva is None:
            return False
        try:
            self.db.delete(reserva)
            self.db.commit()
        except SQLAlchemyError:
            self.db.rollback()
            raise
        return True
    
    def get_reserva_by_idempotency_key(self, idempotency_key: str) -> Reserva | None:
        query = select(Reserva).where(Reserva.idempotency_key == idempotency_key)
        return self.db.scalars(query).first()
