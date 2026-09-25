import os
import sys
from concurrent import futures
from datetime import date
import grpc

from .database import engine, Base, SessionLocal
from .models import Habitacion
from . import crud
from .protos import habitaciones_pb2 as pb2
from .protos import habitaciones_pb2_grpc as pb2_grpc


class HabitacionesServicer(pb2_grpc.HabitacionesServiceServicer):

    def CrearHabitacion(self, request, context):
        with SessionLocal() as db:
            exito, hab_id, mensaje = crud.crear_habitacion(
                db,
                numero=request.numero.strip(),
                tipo=request.tipo.strip(),
                precio_noche=float(request.precio_noche)
            )
            return pb2.CrearHabitacionResponse(
                exito=exito,
                habitacion_id=hab_id if exito else 0,
                mensaje=mensaje
            )

    def ListarHabitaciones(self, request, context):
        with SessionLocal() as db:
            habitaciones = crud.listar_todas_las_habitaciones(db)
            items = [
                pb2.HabitacionInfo(
                    id=h.id,
                    numero=h.numero,
                    tipo=h.tipo,
                    precio_noche=h.precio_noche
                )
                for h in habitaciones
            ]
            return pb2.ListarHabitacionesResponse(habitaciones=items)

    def ConsultarDisponibilidad(self, request, context):
        try:
            inicio = date.fromisoformat(request.fecha_inicio)
            fin = date.fromisoformat(request.fecha_fin)
        except ValueError:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Formato de fecha inválido. Use YYYY-MM-DD.")
            return pb2.ConsultarDisponibilidadResponse()

        with SessionLocal() as db:
            libres = crud.consultar_disponibilidad(db, inicio, fin)
            items = [
                pb2.HabitacionInfo(
                    id=h.id,
                    numero=h.numero,
                    tipo=h.tipo,
                    precio_noche=h.precio_noche
                )
                for h in libres
            ]
            return pb2.ConsultarDisponibilidadResponse(habitaciones_disponibles=items)

    def ListarDisponibilidad(self, request, context):
        try:
            fecha = date.fromisoformat(request.fecha)
        except ValueError:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Formato de fecha inválido. Use YYYY-MM-DD.")
            return pb2.ListarDisponibilidadResponse()

        with SessionLocal() as db:
            total, num_libres, libres = crud.listar_disponibilidad_por_fecha(db, fecha)
            items = [
                pb2.HabitacionInfo(
                    id=h.id,
                    numero=h.numero,
                    tipo=h.tipo,
                    precio_noche=h.precio_noche
                )
                for h in libres
            ]
            return pb2.ListarDisponibilidadResponse(
                fecha=request.fecha,
                total_habitaciones=total,
                habitaciones_libres=num_libres,
                libres=items
            )

    def AsignarHabitacion(self, request, context):
        try:
            inicio = date.fromisoformat(request.fecha_inicio)
            fin = date.fromisoformat(request.fecha_fin)
        except ValueError:
            return pb2.AsignarHabitacionResponse(
                estado=pb2.DATOS_INVALIDOS,
                habitacion_id=0,
                mensaje="Formato de fecha inválido. Debe ser YYYY-MM-DD."
            )

        habitacion_deseada = request.habitacion_id if request.HasField("habitacion_id") else None

        with SessionLocal() as db:
            estado, hab_id, mensaje = crud.asignar_habitacion(
                db,
                reserva_id=request.reserva_id,
                inicio=inicio,
                fin=fin,
                habitacion_deseada_id=habitacion_deseada
            )
            return pb2.AsignarHabitacionResponse(
                estado=estado,
                habitacion_id=hab_id,
                mensaje=mensaje
            )

    def LiberarHabitacion(self, request, context):
        with SessionLocal() as db:
            liberada, mensaje = crud.liberar_habitacion(db, reserva_id=request.reserva_id)
            return pb2.LiberarHabitacionResponse(
                liberada=liberada,
                mensaje=mensaje
            )

    def ConsultarAsignacion(self, request, context):
        with SessionLocal() as db:
            asignada, hab_id, inicio, fin = crud.consultar_asignacion(db, reserva_id=request.reserva_id)
            resp = pb2.ConsultarAsignacionResponse(asignada=asignada)
            if asignada:
                resp.habitacion_id = hab_id
                resp.fecha_inicio = inicio
                resp.fecha_fin = fin
            return resp


def serve():
    # Inicializar tablas en SQLite
    Base.metadata.create_all(bind=engine)

    port = os.getenv("PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_HabitacionesServiceServicer_to_server(HabitacionesServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"🚀 Servidor gRPC de Habitaciones escuchando en el puerto {port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
