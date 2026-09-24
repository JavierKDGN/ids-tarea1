from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
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

    def create_reserva(self, reserva: ReservaCreate, estado: EstadoReserva = EstadoReserva.PENDIENTE, habitacion_id: int | None = None):
        new_reserva = Reserva(
            **reserva.model_dump(),
            estado=estado,
            habitacion_id=habitacion_id
        )
        try:
            self.db.add(new_reserva)
            self.db.commit()
            self.db.refresh(new_reserva)
            return ReservaResponse.model_validate(new_reserva)

        except IntegrityError:
            self.db.rollback()
            return None     

    def get_reserva_by_id(self, reserva_id: int):
        return self.db.get(Reserva, reserva_id)

    def get_reservas(self):
        reservas = select(Reserva)
        return self.db.scalars(reservas).all()

    def delete_reserva_by_id(self, reserva_id: int):
        reserva = self.get_reserva_by_id(reserva_id)
        if reserva:
            self.db.delete(reserva)
            self.db.commit()
            return True
        return False

    def cambiar_estado_reserva(self, reserva_id: int, nuevo_estado: EstadoReserva):
        reserva = self.get_reserva_by_id(reserva_id)
        if reserva:
            reserva.estado = nuevo_estado
            self.db.commit()
            self.db.refresh(reserva)
            return ReservaResponse.model_validate(reserva)
        return None