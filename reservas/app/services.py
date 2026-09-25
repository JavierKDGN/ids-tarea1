from datetime import date
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session

from .crud import HuespedCRUD, ReservaCRUD
from .models import EstadoReserva, Reserva
from .schema import ReservaCreate, ReservaResponse
from .error_models import *

def _marcar_reparacion(db: Session, reserva_id: int) -> None:
    try:
        crud = ReservaCRUD(db)
        reserva = crud.get_reserva_by_id(reserva_id)
        if reserva and reserva.estado not in (
            EstadoReserva.CONFIRMADA,
            EstadoReserva.CANCELADA
        ):
            crud.cambiar_estado_reserva(reserva_id, EstadoReserva.REPARACION)
    except SQLAlchemyError:
        db.rollback()
        
def crear_reserva(
    db: Session,
    datos: ReservaCreate,
    habitaciones,
    idempotency_key: str | None = None,
) -> ReservaResponse:
    
    if datos.fecha_fin <= datos.fecha_inicio:
        raise DatosInvalidos(
            "La salida debe ser posterior a la entrada"
        )

    if HuespedCRUD(db).get_huesped(datos.huesped_id) is None:
        raise HuespedNoExiste(datos.huesped_id)

    crud = ReservaCRUD(db)
    
    # Reintento REST: devolver la reserva ya creada
    if idempotency_key:
        existente = crud.get_reserva_by_idempotency_key(idempotency_key)

        if existente is not None:
            return ReservaResponse.model_validate(existente)    
    
    try:
        pendiente = crud.create_reserva(
            datos,
            idempotency_key=idempotency_key
        )
        
    except IntegrityError:
        
        if idempotency_key:
            existente = crud.get_reserva_by_idempotency_key(idempotency_key)

            if existente is not None:
                return ReservaResponse.model_validate(existente)

        raise ReservaIncierta()

    try:
        habitacion_id = habitaciones.reservar(
            pendiente.id,
            datos.fecha_inicio,
            datos.fecha_fin,
            habitacion_id=getattr(datos, "habitacion_id", None),
        )
    except (TimeoutError, ConnectionError) as exc:
        _marcar_reparacion(db, pendiente.id)
        raise ReservaIncierta(pendiente.id) from exc

    if habitacion_id is None:
        try:
            crud.delete_reserva_by_id(pendiente.id)
        except SQLAlchemyError as exc:
            db.rollback()
            _marcar_reparacion(db, pendiente.id)
            raise ReservaIncierta(pendiente.id) from exc

        raise SinDisponibilidad(
            "No hay habitación para toda la estadía"
        )

    try:
        confirmada = crud.confirmar_reserva(
            pendiente.id, habitacion_id
        )
    except SQLAlchemyError as exc:
        _marcar_reparacion(db, pendiente.id)
        raise ReservaIncierta(pendiente.id) from exc

    if confirmada is None:
        raise ReservaIncierta(pendiente.id)

    return confirmada


def cancelar_reserva(
    db: Session,
    reserva_id: int,
    habitaciones,
) -> ReservaResponse:
    crud = ReservaCRUD(db)
    reserva = crud.get_reserva_by_id(reserva_id)

    if reserva is None:
        raise ReservaNoExiste(reserva_id)

    if reserva.estado == EstadoReserva.CANCELADA:
        return ReservaResponse.model_validate(reserva)

    if reserva.estado != EstadoReserva.CONFIRMADA:
        raise EstadoInvalido(
            "Solo se puede cancelar una reserva confirmada"
        )

    if reserva.habitacion_id is None:
        raise EstadoInvalido(
            "La reserva confirmada no tiene habitación"
        )

    solicitada = crud.cambiar_estado_reserva(
        reserva_id, EstadoReserva.CANCELACION_SOLICITADA
    )
    if solicitada is None:
        raise ReservaNoExiste(reserva_id)

    try:
        liberada = habitaciones.liberar(reserva_id)
    except (TimeoutError, ConnectionError) as exc:
        _marcar_reparacion(db, reserva_id)
        raise ReservaIncierta(reserva_id) from exc

    if not liberada:
        _marcar_reparacion(db, reserva_id)
        raise ReservaIncierta(reserva_id)

    try:
        cancelada = crud.cambiar_estado_reserva(
            reserva_id, EstadoReserva.CANCELADA
        )
    except SQLAlchemyError as exc:
        _marcar_reparacion(db, reserva_id)
        raise ReservaIncierta(reserva_id) from exc

    if cancelada is None:
        raise ReservaIncierta(reserva_id)

    return cancelada

def resolver_reserva(
    db: Session,
    reserva_id: int,
    habitaciones,
) -> ReservaResponse | None:
    crud = ReservaCRUD(db)
    reserva = crud.get_reserva_by_id(reserva_id)

    if reserva is None:
        raise ReservaNoExiste(reserva_id)

    if reserva.estado == EstadoReserva.CONFIRMADA:
        raise EstadoInvalido("La reserva ya esta confirmada")

    if reserva.estado == EstadoReserva.CANCELADA:
        return ReservaResponse.model_validate(reserva)

    try:
        asignacion_actual = habitaciones.consultar_asignacion(
            reserva_id
        )
    except (TimeoutError, ConnectionError) as exc:
        _marcar_reparacion(db, reserva_id)
        raise ReservaIncierta(reserva_id) from exc

    if reserva.habitacion_id is None:

        if asignacion_actual is not None:
            try:
                liberada = habitaciones.liberar(reserva_id)
            except (TimeoutError, ConnectionError) as exc:
                _marcar_reparacion(db, reserva_id)
                raise ReservaIncierta(reserva_id) from exc

            if not liberada:
                _marcar_reparacion(db, reserva_id)
                raise ReservaIncierta(reserva_id)

        try:
            crud.delete_reserva_by_id(reserva_id)
        except SQLAlchemyError as exc:
            db.rollback()
            _marcar_reparacion(db, reserva_id)
            raise ReservaIncierta(reserva_id) from exc

        return None

    if asignacion_actual is not None:
        if asignacion_actual != reserva.habitacion_id:
            raise ReservaIncierta(reserva_id)

        try:
            liberada = habitaciones.liberar(reserva_id)
        except (TimeoutError, ConnectionError) as exc:
            _marcar_reparacion(db, reserva_id)
            raise ReservaIncierta(reserva_id) from exc

        if not liberada:
            _marcar_reparacion(db, reserva_id)
            raise ReservaIncierta(reserva_id)

    try:
        cancelada = crud.cambiar_estado_reserva(
            reserva_id, EstadoReserva.CANCELADA
        )
    except SQLAlchemyError as exc:
        _marcar_reparacion(db, reserva_id)
        raise ReservaIncierta(reserva_id) from exc

    if cancelada is None:
        raise ReservaIncierta(reserva_id)

    return cancelada