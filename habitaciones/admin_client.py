"""
Script administrativo y de prueba para interactuar con el servicio gRPC de Habitaciones.
Permite registrar habitaciones, consultar disponibilidad y probar asignaciones mediante gRPC.
"""
import sys
import grpc
from app.protos import habitaciones_pb2 as pb2
from app.protos import habitaciones_pb2_grpc as pb2_grpc


def get_stub(host="localhost:50051"):
    channel = grpc.insecure_channel(host)
    return pb2_grpc.HabitacionesServiceStub(channel)


def crear_habitacion(stub, numero: str, tipo: str, precio: float):
    req = pb2.CrearHabitacionRequest(numero=numero, tipo=tipo, precio_noche=precio)
    resp = stub.CrearHabitacion(req)
    print(f"[{'OK' if resp.exito else 'INFO'}] Crear {numero}: ID={resp.habitacion_id} - {resp.mensaje}")
    return resp


def listar_habitaciones(stub):
    req = pb2.ListarHabitacionesRequest()
    resp = stub.ListarHabitaciones(req)
    print(f"\n--- Total habitaciones registradas: {len(resp.habitaciones)} ---")
    for h in resp.habitaciones:
        print(f"  • ID {h.id} | Hab {h.numero} | Tipo: {h.tipo} | ${h.precio_noche:,.0f}/noche")
    return resp.habitaciones


def sembrar_catalogo_demo(stub):
    print("\nRegistrando catálogo inicial de habitaciones vía gRPC...")
    habitaciones_demo = [
        ("101", "Simple", 45000.0),
        ("102", "Simple", 45000.0),
        ("201", "Doble", 70000.0),
        ("202", "Doble", 70000.0),
        ("301", "Suite Matrimonial", 120000.0),
        ("302", "Suite Presidencial", 180000.0),
    ]
    for num, tipo, precio in habitaciones_demo:
        crear_habitacion(stub, num, tipo, precio)


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "localhost:50051"
    stub = get_stub(host)

    if len(sys.argv) > 2 and sys.argv[2] == "crear":
        # python admin_client.py localhost:50051 crear 105 Suite 95000
        num = sys.argv[3]
        tipo = sys.argv[4] if len(sys.argv) > 4 else "Simple"
        precio = float(sys.argv[5]) if len(sys.argv) > 5 else 50000.0
        crear_habitacion(stub, num, tipo, precio)
    elif len(sys.argv) > 2 and sys.argv[2] == "listar":
        listar_habitaciones(stub)
    else:
        # Por defecto, sembrar demo y listar
        sembrar_catalogo_demo(stub)
        listar_habitaciones(stub)
