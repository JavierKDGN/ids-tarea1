class ErrorReserva(Exception):
    pass


class DatosInvalidos(ErrorReserva):
    pass


class HuespedNoExiste(ErrorReserva):
    pass


class ReservaNoExiste(ErrorReserva):
    pass


class EstadoInvalido(ErrorReserva):
    pass


class SinDisponibilidad(ErrorReserva):
    pass

class ReservaIncierta(ErrorReserva):
    def __init__(self, reserva_id: int):
        self.reserva_id = reserva_id
        super().__init__(f"No se conoce el resultado de la reserva {reserva_id}")
