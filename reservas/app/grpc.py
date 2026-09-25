from datetime import date
from threading import Lock
from enum import Enum

class __TiempoFallo(Enum):
    ANTES = "antes", # pre asignacion
    DESPUES = "despues" # post asignacion

class MockHabitacion:

    def __init__(self, habitacion_id: int=1):
        self.id = habitacion_id
        # {reserva_id : (inicio, fin)}
        self._asignaciones: dict[int, tuple[date, date]] = {}
        self._cerradas: set[int] = set()
        self._lock = Lock()

        self._fallo_reserva: __TiempoFallo | None = None
        self._fallo_liberacion: __TiempoFallo | None = None
        self._fallo_consulta: __TiempoFallo | None = None

    def _hay_solapamiento_fechas(self, inicio: date, fin: date) -> bool:
        for i, f in self._asignaciones.values():
            if inicio < f and i < fin:
                return True
        return False

    def revisar_disponibilidad(self, inicio: date, fin: date) -> bool:
        if inicio >= fin:
            raise ValueError("La salida debe ser despues de la entrada")

        with self._lock:
            # False -> fecha disponible
            # True -> fecha ocupada
            return not self._hay_solapamiento_fechas(inicio, fin)

    def reservar(self, reserva_id, inicio, fin) -> int | None:
        """Devuelve el ID de habitacion o None si no hay disponibilidad"""
        if inicio >= fin:
            raise ValueError("La salida debe ser despues de la entrada")
        with self._lock:
            # habitacion no respodne
            if self._fallo_reserva == __TiempoFallo.ANTES:
                self._fallo_reserva = None
                raise TimeoutError("Habitaciones no respondio antes de asignar")

            # solicitud repetida
            if reserva_id in self._cerradas:
                return None

            # reserva repetida
            asignacion_previa = self._asignaciones.get(reserva_id)
            if asignacion_previa is not None:
                if asignacion_previa != (inicio, fin):
                    raise ValueError(
                        "El ID de reserva ya esta asociado a otras fechas"
                    )
                return self.id

            # habitacion ocupada
            if self._hay_solapamiento_fechas(inicio, fin):
                return None

            # asignamos la habitacion a la reserva
            self._asignaciones[reserva_id] = (inicio, fin)

            if self._fallo_reserva == __TiempoFallo.DESPUES:
                self._fallo_reserva = None
                raise TimeoutError(
                    "Habitacion asignada pero no hay respuesta"
                )
            
            return self.id

    def liberar(self, reserva_id: int) -> bool:
        """Libera esta reserva"""
        with self._lock:
            if self._fallo_liberacion == "antes":
                self._fallo_liberacion = None
                raise TimeoutError("Habitacion no respondio antes de liberar")

            self._asignaciones.pop(reserva_id, None)
            self._cerradas.add(reserva_id)

            if self._fallo_liberacion == __TiempoFallo.DESPUES:
                self._fallo_liberacion = None
                raise TimeoutError(
                    "Habitaciones liberadas, pero se perdio la respuesta"
                )

            return True

    def consultar_asignacion(self, reserva_id) -> int | None:
        """Consulta la asignacion de una reserva"""
        with self._lock:
            if self._fallo_consulta:
                self._fallo_consulta = False
                raise TimeoutError("Habitaciones no respondio a la consulta")
            if reserva_id in self._asignaciones:
                return self.id
            return None

    def simular_timeout_reserva(self, despues_de_asignar: bool = False) -> None:
        with self._lock:
            self._fallo_reserva = (
                __TiempoFallo.DESPUES if despues_de_asignar else __TiempoFallo.ANTES
            )

    def simular_timeout_liberacion(self, despues_de_liberar: bool = False) -> None:
        with self._lock:
            self._fallo_liberacion = (
                __TiempoFallo.DESPUES if despues_de_liberar else __TiempoFallo.ANTES
            )

    def simular_timeout_consulta(self) -> None:
        with self._lock:
            self._fallo_consulta = True
            