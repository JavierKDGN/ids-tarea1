from datetime import date, timedelta
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from .models import Habitacion, AsignacionHabitacion
from .protos import habitaciones_pb2 as pb2


def crear_habitacion(db: Session, numero: str, tipo: str, precio_noche: float) -> Tuple[bool, int, str]:
    existente = db.scalars(select(Habitacion).where(Habitacion.numero == numero)).first()
    if existente:
        return False, existente.id, f"La habitación {numero} ya está registrada."

    nueva = Habitacion(numero=numero, tipo=tipo, precio_noche=precio_noche)
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return True, nueva.id, f"Habitación {numero} creada exitosamente."


def listar_todas_las_habitaciones(db: Session) -> List[Habitacion]:
    return list(db.scalars(select(Habitacion).order_by(Habitacion.numero)).all())


def habitacion_esta_libre(db: Session, habitacion_id: int, inicio: date, fin: date) -> bool:
    """Verifica si una habitación está libre en el intervalo semiabierto [inicio, fin)."""
    solapamientos = db.scalars(
        select(AsignacionHabitacion).where(
            and_(
                AsignacionHabitacion.habitacion_id == habitacion_id,
                AsignacionHabitacion.activa == True,
                AsignacionHabitacion.fecha_inicio < fin,
                AsignacionHabitacion.fecha_fin > inicio
            )
        )
    ).all()
    return len(solapamientos) == 0


def consultar_disponibilidad(db: Session, inicio: date, fin: date) -> List[Habitacion]:
    """Retorna todas las habitaciones libres en el rango [inicio, fin)."""
    todas = listar_todas_las_habitaciones(db)
    libres = []
    for hab in todas:
        if habitacion_esta_libre(db, hab.id, inicio, fin):
            libres.append(hab)
    return libres


def listar_disponibilidad_por_fecha(db: Session, fecha: date) -> Tuple[int, int, List[Habitacion]]:
    """Consulta la disponibilidad para la noche de la fecha indicada [fecha, fecha + 1 día)."""
    inicio = fecha
    fin = fecha + timedelta(days=1)
    todas = listar_todas_las_habitaciones(db)
    libres = [hab for hab in todas if habitacion_esta_libre(db, hab.id, inicio, fin)]
    return len(todas), len(libres), libres


def asignar_habitacion(
    db: Session,
    reserva_id: int,
    inicio: date,
    fin: date,
    habitacion_deseada_id: Optional[int] = None
) -> Tuple[int, int, str]:
    """
    Asigna una habitación a una reserva con soporte para:
    - Intervalo semiabierto [inicio, fin)
    - Idempotencia por reserva_id
    - Asignación híbrida (específica o automática)
    Retorna: (EstadoResultadoAsignacion, habitacion_id, mensaje)
    """
    if inicio >= fin:
        return pb2.DATOS_INVALIDOS, 0, "La fecha de salida debe ser posterior a la de entrada."

    # 1. Comprobar Idempotencia: ¿Esta reserva ya tiene asignación activa?
    asignacion_previa = db.scalars(
        select(AsignacionHabitacion).where(
            and_(
                AsignacionHabitacion.reserva_id == reserva_id,
                AsignacionHabitacion.activa == True
            )
        )
    ).first()

    if asignacion_previa is not None:
        if asignacion_previa.fecha_inicio == inicio and asignacion_previa.fecha_fin == fin:
            return (
                pb2.YA_ASIGNADA,
                asignacion_previa.habitacion_id,
                "Reserva ya asignada previamente (reintento idempotente)."
            )
        else:
            return (
                pb2.DATOS_INVALIDOS,
                0,
                "El ID de reserva ya está asociado a un rango de fechas diferente."
            )

    # 2. Si se solicitó una habitación específica
    if habitacion_deseada_id and habitacion_deseada_id > 0:
        hab = db.get(Habitacion, habitacion_deseada_id)
        if not hab:
            return pb2.NO_DISPONIBLE, 0, f"La habitación con ID {habitacion_deseada_id} no existe."

        if not habitacion_esta_libre(db, hab.id, inicio, fin):
            return pb2.NO_DISPONIBLE, 0, f"La habitación {hab.numero} está ocupada en esas fechas."

        hab_elegida_id = hab.id
    else:
        # 3. Asignación automática: buscar la primera habitación libre
        libres = consultar_disponibilidad(db, inicio, fin)
        if not libres:
            return pb2.NO_DISPONIBLE, 0, "No hay habitaciones disponibles para las fechas seleccionadas."
        hab_elegida_id = libres[0].id

    # 4. Registrar la asignación
    nueva_asignacion = AsignacionHabitacion(
        habitacion_id=hab_elegida_id,
        reserva_id=reserva_id,
        fecha_inicio=inicio,
        fecha_fin=fin,
        activa=True
    )
    db.add(nueva_asignacion)
    db.commit()

    return pb2.ASIGNADA, hab_elegida_id, "Habitación asignada exitosamente."


def liberar_habitacion(db: Session, reserva_id: int) -> Tuple[bool, str]:
    """Libera idempotentemente la habitación asignada a una reserva."""
    asignaciones = db.scalars(
        select(AsignacionHabitacion).where(
            and_(
                AsignacionHabitacion.reserva_id == reserva_id,
                AsignacionHabitacion.activa == True
            )
        )
    ).all()

    if not asignaciones:
        return True, "No había asignaciones activas para esta reserva (ya liberada)."

    for a in asignaciones:
        a.activa = False

    db.commit()
    return True, f"Se liberó la reserva {reserva_id} exitosamente."


def consultar_asignacion(db: Session, reserva_id: int) -> Tuple[bool, Optional[int], Optional[str], Optional[str]]:
    """Consulta si una reserva ya tiene una habitación asignada (para recuperación de fallos T7)."""
    asignacion = db.scalars(
        select(AsignacionHabitacion).where(
            and_(
                AsignacionHabitacion.reserva_id == reserva_id,
                AsignacionHabitacion.activa == True
            )
        )
    ).first()

    if asignacion:
        return (
            True,
            asignacion.habitacion_id,
            asignacion.fecha_inicio.isoformat(),
            asignacion.fecha_fin.isoformat()
        )
    return False, None, None, None
