"""
Experimento A — Efecto del timeout ante la caída de Habitaciones (T7 / D4)
============================================================================

Pregunta que responde: ¿cómo protege un timeout al llamador (Reservas)
cuando la dependencia (Habitaciones) no responde, y qué se pierde al
acortarlo o alargarlo?

Este experimento alimenta directamente el ADR D4 (resiliencia y modos de
falla) con datos medidos en lugar de solo la descripción cualitativa que
ya tienen en decisiones.md / DEC-08.

Requisito previo (una sola vez)
--------------------------------
Por defecto, GrpcHabitacionesClient usa un timeout fijo de 2.0s. Para
poder comparar 1s / 2s / 5s hay que hacerlo configurable por variable de
entorno. Aplica este cambio en `reservas/app/grpc.py`:

    def __init__(self, host: str | None = None, timeout: float | None = None):
        import os
        import grpc
        ...
        if timeout is None:
            timeout = float(os.getenv("HABITACIONES_GRPC_TIMEOUT", "2.0"))
        self.timeout = timeout

Y agrega en `.env.example` / `.env`:
    HABITACIONES_GRPC_TIMEOUT=2.0

Y en `compose.yaml`, dentro de `reservas-api.environment`:
    - HABITACIONES_GRPC_TIMEOUT=${HABITACIONES_GRPC_TIMEOUT:-2.0}

Reproducibilidad (instrucciones para el informe)
-------------------------------------------------
1. Sistema sano:
     docker compose up -d
     python experimentos/experimento_a_timeout.py --label sano --n 15

2. Apagar Habitaciones y medir con el timeout actual (2s):
     docker compose stop habitaciones-grpc
     python experimentos/experimento_a_timeout.py --label caida_2s --n 15

3. Cambiar el timeout y repetir (edita HABITACIONES_GRPC_TIMEOUT en .env):
     docker compose up -d --build reservas-api
     python experimentos/experimento_a_timeout.py --label caida_1s --n 15
     # repetir con HABITACIONES_GRPC_TIMEOUT=5 -> --label caida_5s

4. Restaurar el servicio:
     docker compose start habitaciones-grpc

5. Analizar todo lo acumulado:
     python experimentos/graficar_timeout.py
"""
import argparse
import csv
import random
import time
from datetime import date, timedelta
from pathlib import Path

import requests

BASE_URL = "http://localhost"
API_KEY = "hotel-secret-key-2026"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
CSV_PATH = Path(__file__).resolve().parent / "resultados_timeout_con_pause.csv"


def obtener_o_crear_huesped() -> int:
    resp = requests.get(f"{BASE_URL}/v1/huespedes", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    huespedes = resp.json()
    if huespedes:
        return huespedes[0]["id"]

    resp = requests.post(
        f"{BASE_URL}/v1/huespedes",
        headers=HEADERS,
        json={
            "nombre": "Experimento Timeout",
            "telefono": "+56900000000",
            "email": "experimento.timeout@udec.cl",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def medir_una_reserva(huesped_id: int, offset_dias: int) -> dict:
    # Fechas muy espaciadas entre sí para garantizar que nunca compitan
    # por la misma habitación entre intentos (lo que mediríamos aquí es
    # el efecto del timeout, no el de la disponibilidad).
    inicio = date(2029, 1, 1) + timedelta(days=offset_dias * 10)
    fin = inicio + timedelta(days=3)
    body = {
        "huesped_id": huesped_id,
        "fecha_inicio": inicio.isoformat(),
        "fecha_fin": fin.isoformat(),
    }

    t0 = time.perf_counter()
    try:
        resp = requests.post(f"{BASE_URL}/v1/reservas", headers=HEADERS, json=body, timeout=30)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {"status_code": str(resp.status_code), "latencia_ms": round(elapsed_ms, 1), "detalle": ""}
    except requests.exceptions.RequestException as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return {"status_code": "ERROR_CONEXION", "latencia_ms": round(elapsed_ms, 1), "detalle": str(exc)}


def correr_escenario(label: str, n: int) -> None:
    huesped_id = obtener_o_crear_huesped()
    filas = []
    offset_base = random.randint(0, 5000)  # evita chocar con corridas anteriores

    print(f"Ejecutando escenario '{label}' ({n} solicitudes)...")
    for i in range(n):
        resultado = medir_una_reserva(huesped_id, offset_base + i)
        resultado["label"] = label
        resultado["intento"] = i + 1
        filas.append(resultado)
        print(f"  [{i + 1}/{n}] status={resultado['status_code']:>15} latencia={resultado['latencia_ms']:>8} ms")

    nuevo_archivo = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "intento", "status_code", "latencia_ms", "detalle"])
        if nuevo_archivo:
            writer.writeheader()
        writer.writerows(filas)

    print(f"\nResultados agregados a: {CSV_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Mide la latencia de POST /v1/reservas bajo distintos escenarios de disponibilidad de Habitaciones."
    )
    parser.add_argument("--label", required=True, help="Nombre del escenario (ej: sano, caida_2s, caida_1s, caida_5s)")
    parser.add_argument("--n", type=int, default=15, help="Número de solicitudes a medir (default: 15)")
    args = parser.parse_args()
    correr_escenario(args.label, args.n)
