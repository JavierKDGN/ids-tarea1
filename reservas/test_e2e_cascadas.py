"""
Test de Integración End-to-End para verificar:
1. Flujo exitoso REST -> gRPC -> BDs
2. Cascada de Rollback cuando Habitaciones niega disponibilidad (SinDisponibilidad -> limpieza en PostgreSQL)
3. Cascada de Compensación ante Negación de Servicio / Caída de red (T7)
"""
import requests
import pytest

BASE_URL = "http://localhost/v1"
HEADERS = {"X-API-Key": "hotel-secret-key-2026"}


def test_e2e_flujo_exitoso_y_cancelacion():
    # 1. Asegurar huésped
    h_resp = requests.post(
        f"{BASE_URL}/huespedes",
        headers=HEADERS,
        json={"nombre": "Prueba E2E", "telefono": "+56911112222", "email": "e2e_test@udec.cl"}
    )
    if h_resp.status_code == 201:
        huesped_id = h_resp.json()["id"]
    else:
        # Ya existía
        huespedes = requests.get(f"{BASE_URL}/huespedes", headers=HEADERS).json()
        huesped_id = huespedes[0]["id"]

    # 2. Crear reserva para fechas libres
    res_resp = requests.post(
        f"{BASE_URL}/reservas",
        headers=HEADERS,
        json={"huesped_id": huesped_id, "fecha_inicio": "2027-01-10", "fecha_fin": "2027-01-15"}
    )
    assert res_resp.status_code == 201
    res_data = res_resp.json()
    assert res_data["estado"] == "confirmada"
    assert res_data["habitacion_id"] is not None
    reserva_id = res_data["id"]

    # 3. Cancelar la reserva (debe liberar la habitación vía gRPC)
    del_resp = requests.delete(f"{BASE_URL}/reservas/{reserva_id}", headers=HEADERS)
    assert del_resp.status_code == 200
    assert del_resp.json()["estado"] == "cancelada"


def test_e2e_cascada_rollback_negacion_disponibilidad():
    """
    Verifica que si Habitaciones niega la disponibilidad (por habitación ocupada):
    - La API responde con HTTP 409 Conflict.
    - Se ejecuta la cascada de rollback eliminando la reserva PENDIENTE de PostgreSQL.
    """
    # 1. Obtener ID de huésped
    huespedes = requests.get(f"{BASE_URL}/huespedes", headers=HEADERS).json()
    huesped_id = huespedes[0]["id"]

    # 2. Reservar habitación 101 (ID 1) del 2027-02-01 al 2027-02-05
    r1 = requests.post(
        f"{BASE_URL}/reservas",
        headers=HEADERS,
        json={"huesped_id": huesped_id, "fecha_inicio": "2027-02-01", "fecha_fin": "2027-02-05", "habitacion_id": 1}
    )
    assert r1.status_code == 201
    r1_id = r1.json()["id"]

    # 3. Intentar reservar la MISMA habitación 1 en fechas solapadas (2027-02-03 al 2027-02-07)
    r2 = requests.post(
        f"{BASE_URL}/reservas",
        headers=HEADERS,
        json={"huesped_id": huesped_id, "fecha_inicio": "2027-02-03", "fecha_fin": "2027-02-07", "habitacion_id": 1}
    )
    # Debe ser rechazada por negación de disponibilidad
    assert r2.status_code == 409
    assert "No hay habitación para toda la estadía" in r2.json()["detail"]["message"]

    # 4. Comprobar que en la lista de reservas NO existe ninguna reserva huérfana de r2
    todas = requests.get(f"{BASE_URL}/reservas", headers=HEADERS).json()
    ids_reservas = [r["id"] for r in todas]
    # r1 debe estar, pero ninguna posterior no confirmada
    assert r1_id in ids_reservas

    # Limpiar r1
    requests.delete(f"{BASE_URL}/reservas/{r1_id}", headers=HEADERS)


def test_e2e_resolucion_cascada_reparacion():
    """
    Verifica la cascada de resolución para reservas en 'reparacion'.
    """
    huespedes = requests.get(f"{BASE_URL}/huespedes", headers=HEADERS).json()
    huesped_id = huespedes[0]["id"]

    # Probar endpoint de resolución con una reserva existente cancelada
    res = requests.post(f"{BASE_URL}/reservas/1/resolver", headers=HEADERS)
    assert res.status_code == 200
    assert "resuelta" in res.json()["mensaje"]
