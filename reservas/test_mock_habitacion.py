import pytest
from datetime import date
from app.grpc import MockHabitacion


def test_asignacion_basica():
    """Prueba que una habitación se asigne correctamente si está libre."""
    mock = MockHabitacion(habitacion_id=101)
    inicio = date(2026, 10, 1)
    fin = date(2026, 10, 5)

    # Debe estar disponible inicialmente
    assert mock.revisar_disponibilidad(inicio, fin) is True

    # Asignar la reserva
    hab_id = mock.reservar(reserva_id=1, inicio=inicio, fin=fin)
    assert hab_id == 101

    # Ya no debe estar disponible en ese rango
    assert mock.revisar_disponibilidad(inicio, fin) is False


def test_intervalo_semiabierto_noches():
    """
    Prueba el requisito de Javier: [fecha_inicio, fecha_final)
    Si alguien sale el día 5, otro huésped PUEDE entrar el mismo día 5.
    """
    mock = MockHabitacion(habitacion_id=101)
    
    # Huésped 1: del 1 al 5 de octubre (noches 1, 2, 3, 4. Check-out el 5)
    hab_1 = mock.reservar(reserva_id=1, inicio=date(2026, 10, 1), fin=date(2026, 10, 5))
    assert hab_1 == 101

    # Huésped 2: entra el 5 y sale el 10 (Check-in el 5)
    # Según intervalo semiabierto, NO debe haber solapamiento
    assert mock.revisar_disponibilidad(date(2026, 10, 5), date(2026, 10, 10)) is True
    hab_2 = mock.reservar(reserva_id=2, inicio=date(2026, 10, 5), fin=date(2026, 10, 10))
    assert hab_2 == 101


def test_rechazo_por_solapamiento():
    """Prueba que si se solapan las fechas, la habitación no se asigne."""
    mock = MockHabitacion(habitacion_id=101)
    mock.reservar(reserva_id=1, inicio=date(2026, 10, 1), fin=date(2026, 10, 5))

    # Solapamiento parcial (del 3 al 7)
    assert mock.revisar_disponibilidad(date(2026, 10, 3), date(2026, 10, 7)) is False
    hab_solapada = mock.reservar(reserva_id=2, inicio=date(2026, 10, 3), fin=date(2026, 10, 7))
    assert hab_solapada is None

    # Solapamiento total interno (del 2 al 4)
    hab_interna = mock.reservar(reserva_id=3, inicio=date(2026, 10, 2), fin=date(2026, 10, 4))
    assert hab_interna is None


def test_idempotencia_mismo_id_reserva():
    """
    Prueba el requisito de Javier:
    'si recibe el mismo id de reserva no deberia hacer nada'
    Debe devolver el mismo ID de habitación sin error ni duplicar.
    """
    mock = MockHabitacion(habitacion_id=101)
    inicio = date(2026, 10, 1)
    fin = date(2026, 10, 5)

    hab_id_primera = mock.reservar(reserva_id=1, inicio=inicio, fin=fin)
    assert hab_id_primera == 101

    # Reintento con el mismo ID de reserva y mismas fechas
    hab_id_reintento = mock.reservar(reserva_id=1, inicio=inicio, fin=fin)
    assert hab_id_reintento == 101


def test_liberar_habitacion():
    """Prueba que al liberar una reserva, las fechas vuelvan a quedar libres."""
    mock = MockHabitacion(habitacion_id=101)
    inicio = date(2026, 10, 1)
    fin = date(2026, 10, 5)

    mock.reservar(reserva_id=1, inicio=inicio, fin=fin)
    assert mock.revisar_disponibilidad(inicio, fin) is False

    # Liberar la reserva 1
    assert mock.liberar(reserva_id=1) is True

    # Las fechas deben volver a estar libres
    assert mock.revisar_disponibilidad(inicio, fin) is True

    # Una nueva reserva ahora puede tomar esas fechas
    hab_nueva = mock.reservar(reserva_id=2, inicio=inicio, fin=fin)
    assert hab_nueva == 101


def test_consultar_asignacion():
    """
    Prueba el requisito de Javier:
    'se deberia poder consultar si un id de reserva ya esta asignado'
    """
    mock = MockHabitacion(habitacion_id=101)
    inicio = date(2026, 10, 1)
    fin = date(2026, 10, 5)

    # Antes de reservar, no existe
    assert mock.consultar_asignacion(reserva_id=1) is None

    # Después de reservar, devuelve el id de habitación
    mock.reservar(reserva_id=1, inicio=inicio, fin=fin)
    assert mock.consultar_asignacion(reserva_id=1) == 101

    # Después de liberar, ya no está asignada
    mock.liberar(reserva_id=1)
    assert mock.consultar_asignacion(reserva_id=1) is None


def test_fallo_timeout_reserva():
    """Prueba la simulación de fallos para resiliencia (T7)."""
    mock = MockHabitacion(habitacion_id=101)
    inicio = date(2026, 10, 1)
    fin = date(2026, 10, 5)

    # Simular caída ANTES de asignar
    mock.simular_timeout_reserva(despues_de_asignar=False)
    with pytest.raises(TimeoutError, match="antes de asignar"):
        mock.reservar(reserva_id=1, inicio=inicio, fin=fin)

    # La habitación sigue libre porque falló antes de asignar
    assert mock.revisar_disponibilidad(inicio, fin) is True

    # Simular caída DESPUÉS de asignar
    mock.simular_timeout_reserva(despues_de_asignar=True)
    with pytest.raises(TimeoutError, match="asignada pero no hay respuesta"):
        mock.reservar(reserva_id=2, inicio=inicio, fin=fin)

    # La habitación SÍ quedó asignada a reserva 2
    assert mock.consultar_asignacion(reserva_id=2) == 101


def test_fallo_timeout_liberacion():
    """Prueba la simulación de timeout al liberar."""
    mock = MockHabitacion(habitacion_id=101)
    inicio = date(2026, 10, 1)
    fin = date(2026, 10, 5)
    mock.reservar(reserva_id=1, inicio=inicio, fin=fin)

    # Simular timeout antes de liberar
    mock.simular_timeout_liberacion(despues_de_liberar=False)
    with pytest.raises(TimeoutError, match="antes de liberar"):
        mock.liberar(reserva_id=1)

    # Simular timeout después de liberar (la asignación se borró pero se perdió la respuesta)
    mock.simular_timeout_liberacion(despues_de_liberar=True)
    with pytest.raises(TimeoutError, match="se perdio la respuesta"):
        mock.liberar(reserva_id=1)


def test_fechas_invalidas():
    """Prueba que salida <= entrada arroje ValueError."""
    mock = MockHabitacion(habitacion_id=101)
    # Misma fecha de entrada y salida
    with pytest.raises(ValueError, match="despues de la entrada"):
        mock.reservar(reserva_id=1, inicio=date(2026, 10, 5), fin=date(2026, 10, 5))

    # Salida antes de entrada
    with pytest.raises(ValueError, match="despues de la entrada"):
        mock.reservar(reserva_id=1, inicio=date(2026, 10, 5), fin=date(2026, 10, 4))


def test_idempotencia_cambio_fechas_conflicto():
    """Si se reutiliza el mismo reserva_id con fechas distintas debe alertar conflicto."""
    mock = MockHabitacion(habitacion_id=101)
    mock.reservar(reserva_id=1, inicio=date(2026, 10, 1), fin=date(2026, 10, 5))

    with pytest.raises(ValueError, match="asociado a otras fechas"):
        mock.reservar(reserva_id=1, inicio=date(2026, 10, 2), fin=date(2026, 10, 6))


def test_reserva_id_ya_cerrada_no_permite_reutilizacion():
    """Si una reserva fue liberada/cerrada, no se puede volver a reservar con ese mismo ID."""
    mock = MockHabitacion(habitacion_id=101)
    mock.reservar(reserva_id=1, inicio=date(2026, 10, 1), fin=date(2026, 10, 5))
    mock.liberar(reserva_id=1)

    # Reintentar reservar con el ID ya cerrado debe ser rechazado (None)
    resultado = mock.reservar(reserva_id=1, inicio=date(2026, 10, 1), fin=date(2026, 10, 5))
    assert resultado is None


def test_fallo_timeout_consulta():
    """Prueba la simulación de timeout en la consulta de asignación."""
    mock = MockHabitacion(habitacion_id=101)
    mock.reservar(reserva_id=1, inicio=date(2026, 10, 1), fin=date(2026, 10, 5))

    mock.simular_timeout_consulta()
    with pytest.raises(TimeoutError, match="no respondio a la consulta"):
        mock.consultar_asignacion(reserva_id=1)

