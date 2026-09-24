from typing import List
from datetime import date
import enum

from sqlalchemy import Enum, Integer, String, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

class Huesped(Base):
    __tablename__ = "huespedes"
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    telefono: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)

    reservas: Mapped[List["Reserva"]] = relationship(back_populates="huesped")

class EstadoReserva(str, enum.Enum):
    PENDIENTE = "pendiente"
    CONFIRMADA = "confirmada"
    REPARACION = "reparacion"
    CANCELACION_SOLICITADA = "cancelacion_solicitada"
    CANCELADA = "cancelada"

class Reserva(Base):
    __tablename__ = "reserva"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    fecha_inicio: Mapped[date] = mapped_column(nullable=False)
    fecha_fin: Mapped[date] = mapped_column(nullable=False)
    estado: Mapped[EstadoReserva] = mapped_column(Enum(EstadoReserva), nullable=False)
    habitacion_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    huesped_id: Mapped[int] = mapped_column(ForeignKey("huespedes.id"), nullable=False)
    huesped: Mapped["Huesped"] = relationship(back_populates="reservas")