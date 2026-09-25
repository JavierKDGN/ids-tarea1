from datetime import date
from threading import Lock
from enum import Enum

class _TiempoFallo(Enum):
    ANTES = "antes" # pre asignacion
    DESPUES = "despues" # post asignacion

class MockHabitacion:

    def __init__(self, habitacion_id: int=1):
        self.id = habitacion_id
        # {reserva_id : (inicio, fin)}
        self._asignaciones: dict[int, tuple[date, date]] = {}
        self._cerradas: set[int] = set()
        self._lock = Lock()

        self._fallo_reserva: _TiempoFallo | None = None
        self._fallo_liberacion: _TiempoFallo | None = None
        self._fallo_consulta: _TiempoFallo | None = None

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
            if self._fallo_reserva == _TiempoFallo.ANTES:
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

            if self._fallo_reserva == _TiempoFallo.DESPUES:
                self._fallo_reserva = None
                raise TimeoutError(
                    "Habitacion asignada pero no hay respuesta"
                )
            
            return self.id

    def liberar(self, reserva_id: int) -> bool:
        """Libera esta reserva"""
        with self._lock:
            if self._fallo_liberacion == _TiempoFallo.ANTES:
                self._fallo_liberacion = None
                raise TimeoutError("Habitacion no respondio antes de liberar")

            self._asignaciones.pop(reserva_id, None)
            self._cerradas.add(reserva_id)

            if self._fallo_liberacion == _TiempoFallo.DESPUES:
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
                _TiempoFallo.DESPUES if despues_de_asignar else _TiempoFallo.ANTES
            )

    def simular_timeout_liberacion(self, despues_de_liberar: bool = False) -> None:
        with self._lock:
            self._fallo_liberacion = (
                _TiempoFallo.DESPUES if despues_de_liberar else _TiempoFallo.ANTES
            )

    def simular_timeout_consulta(self) -> None:
        with self._lock:
            self._fallo_consulta = True


class GrpcHabitacionesClient:
    """Cliente gRPC real que consume el microservicio de Habitaciones."""

    def __init__(self, host: str | None = None, timeout: float = 2.0):
        import os
        import grpc
        from .protos import habitaciones_pb2 as pb2
        from .protos import habitaciones_pb2_grpc as pb2_grpc

        self._grpc = grpc
        self._pb2 = pb2
        self._pb2_grpc = pb2_grpc

        target = host or os.getenv("HABITACIONES_GRPC_HOST", "habitaciones-grpc:50051")
        self.channel = grpc.insecure_channel(target)
        self.stub = pb2_grpc.HabitacionesServiceStub(self.channel)
        self.timeout = timeout

    def _handle_rpc_error(self, exc):
        code = exc.code()
        if code == self._grpc.StatusCode.DEADLINE_EXCEEDED:
            raise TimeoutError(f"Habitaciones no respondió dentro del timeout ({self.timeout}s): {exc.details()}")
        elif code == self._grpc.StatusCode.UNAVAILABLE:
            raise ConnectionError(f"Servicio de Habitaciones no disponible: {exc.details()}")
        else:
            raise ConnectionError(f"Error gRPC [{code}]: {exc.details()}")

    def revisar_disponibilidad(self, inicio: date, fin: date) -> bool:
        try:
            req = self._pb2.ConsultarDisponibilidadRequest(
                fecha_inicio=inicio.isoformat(),
                fecha_fin=fin.isoformat()
            )
            resp = self.stub.ConsultarDisponibilidad(req, timeout=self.timeout)
            return len(resp.habitaciones_disponibles) > 0
        except self._grpc.RpcError as exc:
            self._handle_rpc_error(exc)

    def consultar_disponibilidad(self, inicio: date, fin: date):
        try:
            req = self._pb2.ConsultarDisponibilidadRequest(
                fecha_inicio=inicio.isoformat(),
                fecha_fin=fin.isoformat()
            )
            resp = self.stub.ConsultarDisponibilidad(req, timeout=self.timeout)
            return resp.habitaciones_disponibles
        except self._grpc.RpcError as exc:
            self._handle_rpc_error(exc)

    def listar_disponibilidad(self, fecha: date):
        try:
            req = self._pb2.ListarDisponibilidadRequest(fecha=fecha.isoformat())
            resp = self.stub.ListarDisponibilidad(req, timeout=self.timeout)
            return resp
        except self._grpc.RpcError as exc:
            self._handle_rpc_error(exc)

    def reservar(self, reserva_id: int, inicio: date, fin: date, habitacion_id: int | None = None) -> int | None:
        try:
            req = self._pb2.AsignarHabitacionRequest(
                reserva_id=reserva_id,
                fecha_inicio=inicio.isoformat(),
                fecha_fin=fin.isoformat(),
                habitacion_id=habitacion_id
            )
            resp = self.stub.AsignarHabitacion(req, timeout=self.timeout)

            if resp.estado in (self._pb2.ASIGNADA, self._pb2.YA_ASIGNADA):
                return resp.habitacion_id
            elif resp.estado == self._pb2.NO_DISPONIBLE:
                return None
            elif resp.estado == self._pb2.DATOS_INVALIDOS:
                raise ValueError(resp.mensaje)
            return None
        except self._grpc.RpcError as exc:
            self._handle_rpc_error(exc)

    def liberar(self, reserva_id: int) -> bool:
        try:
            req = self._pb2.LiberarHabitacionRequest(reserva_id=reserva_id)
            resp = self.stub.LiberarHabitacion(req, timeout=self.timeout)
            return resp.liberada
        except self._grpc.RpcError as exc:
            self._handle_rpc_error(exc)

    def consultar_asignacion(self, reserva_id: int) -> int | None:
        try:
            req = self._pb2.ConsultarAsignacionRequest(reserva_id=reserva_id)
            resp = self.stub.ConsultarAsignacion(req, timeout=self.timeout)
            return resp.habitacion_id if resp.asignada else None
        except self._grpc.RpcError as exc:
            self._handle_rpc_error(exc)


_habitaciones_client_singleton = None

def get_habitaciones_client():
    global _habitaciones_client_singleton
    if _habitaciones_client_singleton is None:
        _habitaciones_client_singleton = GrpcHabitacionesClient()
    return _habitaciones_client_singleton

            