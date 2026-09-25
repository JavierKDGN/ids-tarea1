from datetime import date
from typing import List
from sqlalchemy import Integer, String, Float, Date, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Habitacion(Base):
    __tablename__ = "habitaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, default="Simple")
    precio_noche: Mapped[float] = mapped_column(Float, nullable=False, default=50000.0)

    asignaciones: Mapped[List["AsignacionHabitacion"]] = relationship("AsignacionHabitacion", back_populates="habitacion")


class AsignacionHabitacion(Base):
    __tablename__ = "asignaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    habitacion_id: Mapped[int] = mapped_column(ForeignKey("habitaciones.id"), nullable=False, index=True)
    reserva_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    habitacion: Mapped["Habitacion"] = relationship("Habitacion", back_populates="asignaciones")
