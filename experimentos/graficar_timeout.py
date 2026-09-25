"""
Analiza y grafica los resultados acumulados del Experimento A
(resultados_timeout.csv). Ejecutar después de haber corrido
experimento_a_timeout.py para cada escenario (sano, caida_1s, caida_2s, caida_5s...).

Uso:
    python experimentos/graficar_timeout.py
"""
import csv
import statistics
from collections import defaultdict
from pathlib import Path

CSV_PATH = Path(__file__).resolve().parent / "resultados_timeout.csv"
PNG_PATH = Path(__file__).resolve().parent / "grafico_timeout.png"


def cargar_datos() -> dict[str, list[dict]]:
    datos = defaultdict(list)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for fila in csv.DictReader(f):
            datos[fila["label"]].append(fila)
    return datos


def main() -> None:
    if not CSV_PATH.exists():
        print(f"No existe {CSV_PATH} todavía. Corre primero experimento_a_timeout.py para al menos un escenario.")
        return

    datos = cargar_datos()

    encabezado = (
        f"{'Escenario':<15} | {'n':>4} | {'% éxito (2xx)':>14} | "
        f"{'Latencia media (ms)':>20} | {'Mediana (ms)':>13} | {'Desv. estándar':>15}"
    )
    print(encabezado)
    print("-" * len(encabezado))

    resumen = {}
    for label, filas in datos.items():
        latencias = [float(f["latencia_ms"]) for f in filas]
        exitos = sum(1 for f in filas if f["status_code"].startswith("2"))
        media = statistics.mean(latencias)
        mediana = statistics.median(latencias)
        desv = statistics.stdev(latencias) if len(latencias) > 1 else 0.0
        pct_exito = 100 * exitos / len(filas)

        resumen[label] = {"media": media, "mediana": mediana, "desv": desv, "latencias": latencias}
        print(
            f"{label:<15} | {len(filas):>4} | {pct_exito:>13.1f}% | "
            f"{media:>20.1f} | {mediana:>13.1f} | {desv:>15.1f}"
        )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        labels = list(resumen.keys())
        plt.figure(figsize=(8, 5))
        plt.boxplot([resumen[l]["latencias"] for l in labels], labels=labels)
        plt.ylabel("Latencia (ms)")
        plt.title("Latencia de POST /v1/reservas por escenario")
        plt.grid(True, alpha=0.3)
        plt.savefig(PNG_PATH, dpi=150, bbox_inches="tight")
        print(f"\nGráfico guardado en: {PNG_PATH}")
    except ImportError:
        print(
            "\n(matplotlib no está instalado; se omitió el gráfico. "
            "Ejecuta `pip install -r experimentos/requirements.txt`.)"
        )


if __name__ == "__main__":
    main()
