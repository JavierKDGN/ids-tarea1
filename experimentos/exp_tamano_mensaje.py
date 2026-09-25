"""
Experimento B — Tamaño del mensaje: Protocol Buffers (gRPC) vs REST/JSON
==========================================================================

Pregunta que responde: ¿cuánto más compacto es Protobuf que JSON para el
mismo recurso (catálogo de habitaciones), y cómo cambia esa ventaja con
gzip y con el tamaño del catálogo?

Este experimento alimenta directamente el ADR D2 ("REST hacia afuera,
gRPC hacia adentro") con datos concretos en lugar de una justificación
solo cualitativa.

Reproducibilidad
-----------------
No requiere Docker corriendo ni red: construye los mensajes directamente
usando los stubs de Protobuf ya compilados en `reservas/app/protos/`.
Cualquier otro grupo puede reproducirlo ejecutando, desde la raíz del
repositorio:

    pip install -r experimentos/requirements.txt
    python experimentos/experimento_b_tamano_mensaje.py

Metodología
-----------
1. Se genera un catálogo sintético de N habitaciones (mismos valores en
   ambos formatos, para que la comparación sea justa).
2. Se serializa ese catálogo como:
     a) Protobuf  -> HabitacionesResponse.SerializeToString()
     b) JSON      -> json.dumps(...).encode("utf-8")
     c) JSON+gzip -> gzip.compress(json_bytes)
3. Se repite para varios tamaños de catálogo (10, 50, 200, 1000) para
   observar si la ventaja de Protobuf se mantiene, crece o se achica.
4. Se guardan los resultados en CSV y se genera un gráfico comparativo.
"""
import csv
import gzip
import json
import sys
from pathlib import Path

# Los stubs generados (habitaciones_pb2.py) permiten import relativo O
# absoluto (ver el try/except en habitaciones_pb2_grpc.py), así que basta
# con agregar su carpeta al sys.path para importarlos sin depender del
# paquete `app` completo de ningún servicio.
STUBS_DIR = Path(__file__).resolve().parent.parent / "reservas" / "app" / "protos"
sys.path.insert(0, str(STUBS_DIR))

import habitaciones_pb2 as pb2  # noqa: E402  (import después de tocar sys.path)


TAMANOS_CATALOGO = [10, 50, 200, 1000]
TIPOS_HABITACION = ["Simple", "Doble", "Suite Matrimonial", "Suite Presidencial"]

CSV_PATH = Path(__file__).resolve().parent / "resultados_tamano_mensaje.csv"
PNG_PATH = Path(__file__).resolve().parent / "grafico_tamano_mensaje.png"


def generar_catalogo(n: int) -> list[dict]:
    """Genera n habitaciones sintéticas, con los mismos valores para ambos formatos."""
    return [
        {
            "id": i,
            "numero": f"{100 + i}",
            "tipo": TIPOS_HABITACION[i % len(TIPOS_HABITACION)],
            "precio_noche": 45000.0 + (i % 5) * 10000.0,
        }
        for i in range(n)
    ]


def serializar_protobuf(catalogo: list[dict]) -> bytes:
    respuesta = pb2.ListarHabitacionesResponse(
        habitaciones=[
            pb2.HabitacionInfo(
                id=h["id"],
                numero=h["numero"],
                tipo=h["tipo"],
                precio_noche=h["precio_noche"],
            )
            for h in catalogo
        ]
    )
    return respuesta.SerializeToString()


def serializar_json(catalogo: list[dict]) -> bytes:
    # Misma forma que devolvería la API REST para un recurso equivalente
    payload = {"habitaciones": catalogo}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def main() -> None:
    filas = []

    encabezado = (
        f"{'N':>6} | {'Protobuf':>9} | {'Protobuf+gz':>12} | {'JSON':>8} | "
        f"{'JSON+gzip':>10} | {'Ahorro pb vs JSON':>18} | {'Ahorro pb vs JSON+gz':>21}"
    )
    print(encabezado)
    print("-" * len(encabezado))

    for n in TAMANOS_CATALOGO:
        catalogo = generar_catalogo(n)

        pb_bytes = serializar_protobuf(catalogo)
        pb_gzip_bytes = gzip.compress(pb_bytes)
        json_bytes = serializar_json(catalogo)
        json_gzip_bytes = gzip.compress(json_bytes)

        ahorro_vs_json = 100 * (1 - len(pb_bytes) / len(json_bytes))
        ahorro_vs_gzip = 100 * (1 - len(pb_bytes) / len(json_gzip_bytes))

        print(
            f"{n:>6} | {len(pb_bytes):>9} | {len(pb_gzip_bytes):>12} | {len(json_bytes):>8} | "
            f"{len(json_gzip_bytes):>10} | {ahorro_vs_json:>17.1f}% | {ahorro_vs_gzip:>20.1f}%"
        )

        filas.append(
            {
                "n_habitaciones": n,
                "protobuf_bytes": len(pb_bytes),
                "protobuf_gzip_bytes": len(pb_gzip_bytes),
                "json_bytes": len(json_bytes),
                "json_gzip_bytes": len(json_gzip_bytes),
                "ahorro_protobuf_vs_json_pct": round(ahorro_vs_json, 2),
                "ahorro_protobuf_vs_json_gzip_pct": round(ahorro_vs_gzip, 2),
            }
        )

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        writer.writeheader()
        writer.writerows(filas)
    print(f"\nResultados guardados en: {CSV_PATH}")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        ns = [f["n_habitaciones"] for f in filas]
        pb = [f["protobuf_bytes"] for f in filas]
        pbgz = [f["protobuf_gzip_bytes"] for f in filas]
        js = [f["json_bytes"] for f in filas]
        jsgz = [f["json_gzip_bytes"] for f in filas]

        plt.figure(figsize=(8, 5))
        plt.plot(ns, pb, marker="o", label="Protobuf")
        plt.plot(ns, pbgz, marker="o", label="Protobuf + gzip")
        plt.plot(ns, js, marker="o", label="JSON")
        plt.plot(ns, jsgz, marker="o", label="JSON + gzip")
        plt.xlabel("Cantidad de habitaciones en la respuesta")
        plt.ylabel("Tamaño del mensaje (bytes)")
        plt.title("Tamaño del mensaje: Protobuf vs JSON vs JSON + gzip")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(PNG_PATH, dpi=150, bbox_inches="tight")
        print(f"Gráfico guardado en: {PNG_PATH}")
    except ImportError:
        print(
            "\n(matplotlib no está instalado; se omitió el gráfico. "
            "Ejecuta `pip install -r experimentos/requirements.txt`.)"
        )


if __name__ == "__main__":
    main()
