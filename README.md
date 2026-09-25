# Sistema de Integración Hotelera — Cadena Hotelera Costanera (Forma H)

Solución de integración de sistemas desarrollada para el **Encargo de Unidad 1** de la asignatura *Integración de Sistemas* (Ingeniería Civil Informática, Universidad de Concepción).

---

## 1. Arquitectura de Referencia: "REST hacia afuera, gRPC hacia adentro"

El sistema resuelve la problemática de integración entre dos dominios que operaban de forma desacoplada:

```
  [ Clientes Externos / Swagger UI / Web ]
                     │
                     │  HTTP REST (JSON) + Autenticación X-API-Key
                     ▼
         ┌───────────────────────┐
         │     reservas-api      │ ────▶ [ reservas-bd (PostgreSQL) ]
         │      (Puerto 80)      │
         └───────────────────────┘
                     │
                     │  gRPC / Protocol Buffers (Alta velocidad, bajo overhead)
                     ▼
         ┌───────────────────────┐
         │   habitaciones-grpc   │ ────▶ [ habitaciones.db (SQLite) ]
         │    (Puerto 50051)     │
         └───────────────────────┘
```

* **Servicio de Reservas (API REST Pública - `/v1`):** Punto de entrada expuesto hacia el exterior. Administra huéspedes y estadías, persistiendo en su propia base de datos PostgreSQL.
* **Servicio de Habitaciones (Microservicio Interno gRPC):** Fuente de verdad sobre el inventario y disponibilidad de habitaciones por fecha. Utiliza SQLite y expone un contrato binario tipado en el puerto `50051`.
* **Aislamiento de Almacenes (T5):** Ningún servicio accede a la base de datos del otro; toda consulta o bloqueo se orquesta mediante contratos formales.

---

## 2. Contratos Versionados (T3)

* **Contrato gRPC:** [`contracts/habitaciones.proto`](contracts/habitaciones.proto)
  * Define los procedimientos `CrearHabitacion`, `ListarHabitaciones`, `ConsultarDisponibilidad`, `ListarDisponibilidad`, `AsignarHabitacion`, `LiberarHabitacion` y `ConsultarAsignacion`.
  * Maneja intervalos de noches semiabiertos `[fecha_inicio, fecha_fin)` y asignación idempotente por `reserva_id`.
* **Contrato REST:** [`contracts/openapi.yaml`](contracts/openapi.yaml)
  * Especificación OpenAPI 3.1 con los endpoints `/v1/huespedes`, `/v1/reservas` y `/v1/disponibilidad`.

---

## 3. Puesta en Marcha con Docker (T1)

### Requisitos Previos

* Docker y Docker Compose instalados.

### 1. Variables de Entorno

Crea tu archivo `.env` a partir de la plantilla:

```bash
cp .env.example .env
```

*(Valores por defecto preconfigurados: credenciales de PostgreSQL, ruta de SQLite y `API_KEY=hotel-secret-key-2026`).*

### 2. Levantar el Ecosistema Completo

Ejecuta un único comando para compilar y encender los contenedores:

```bash
docker compose up -d --build
```

### 3. Verificar Estado de los Contenedores

```bash
docker compose ps
```

Deberás ver los 3 servicios activos:

* `reservas-bd` (PostgreSQL - Puerto 5432, estado *healthy*)
* `reservas-api` (FastAPI - Puerto 80)
* `habitaciones-grpc` (Servidor gRPC - Puerto 50051)

---

## 4. Tour Interactivo de Pruebas

Puedes probar todo el sistema paso a paso siguiendo esta guía:

### Paso 1: Explorar el Servicio gRPC directamente

El servicio de Habitaciones cuenta con un cliente administrativo de prueba en `habitaciones/admin_client.py`:

```bash
# 1. Sembrar un catálogo de habitaciones de prueba vía gRPC:
python habitaciones/admin_client.py localhost:50051

# 2. Consultar el inventario de habitaciones registradas:
python habitaciones/admin_client.py localhost:50051 listar

# 3. Registrar una nueva habitación personalizada vía gRPC:
# Uso: python habitaciones/admin_client.py <host> crear <numero> <tipo> <precio_noche>
python habitaciones/admin_client.py localhost:50051 crear 401 Penthouse 250000
```

---

### Paso 2: Probar la API REST vía Swagger UI (Navegador)

1. Abre en tu navegador: [http://localhost/docs](http://localhost/docs)
2. Haz clic en el botón verde **Authorize** (arriba a la derecha).
3. En el campo `X-API-Key`, ingresa:

   ```text
   hotel-secret-key-2026
   ```

4. Haz clic en **Authorize** y luego **Close**. Ahora puedes ejecutar cualquier endpoint directamente desde la interfaz web interactiva.

---

### Paso 3: Flujo Completo por Terminal (PowerShell / Bash)

#### A. Registrar un Huésped (`POST /v1/huespedes`)

```powershell
$headers = @{"X-API-Key" = "hotel-secret-key-2026"}
$body = @{
    nombre = "Constanza Valenzuela"
    telefono = "+56987654321"
    email = "constanza@udec.cl"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost/v1/huespedes" -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

#### B. Consultar Disponibilidad a través de gRPC (`GET /v1/disponibilidad`)

```powershell
Invoke-RestMethod -Uri "http://localhost/v1/disponibilidad?fecha_inicio=2026-11-01&fecha_fin=2026-11-05" -Headers $headers
```

#### C. Crear una Reserva (`POST /v1/reservas`)

*(Reservas consulta por gRPC a Habitaciones, bloquea la habitación y confirma la estadía)*:

```powershell
$reserva = @{
    huesped_id = 1
    fecha_inicio = "2026-11-01"
    fecha_fin = "2026-11-05"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost/v1/reservas" -Method Post -Headers $headers -ContentType "application/json" -Body $reserva
```

*Respuesta esperada:* Estado `confirmada` y número de `habitacion_id` asignado.

#### D. Cancelar y Liberar Estadía (`DELETE /v1/reservas/{id}`)

```powershell
Invoke-RestMethod -Uri "http://localhost/v1/reservas/1" -Method Delete -Headers $headers
```

*Respuesta esperada:* Estado `cancelada`. La habitación queda automáticamente libre en gRPC.

---

### Paso 4: Demostración del Modo de Falla (Requisito T7)

Para evidenciar la resiliencia del sistema cuando la dependencia interna se cae:

1. **Detén intencionalmente el servicio gRPC:**

   ```bash
   docker compose stop habitaciones-grpc
   ```

2. **Intenta realizar una nueva reserva:**

   ```powershell
   $reserva_falla = @{
       huesped_id = 1
       fecha_inicio = "2026-12-01"
       fecha_fin = "2026-12-05"
   } | ConvertTo-Json

   try {
       Invoke-RestMethod -Uri "http://localhost/v1/reservas" -Method Post -Headers $headers -ContentType "application/json" -Body $reserva_falla
   } catch {
       $_.ErrorDetails.Message
   }
   ```

   *Respuesta esperada:* **`HTTP 503 Service Unavailable`** con JSON explicativo:

   ```json
   {
     "detail": {
       "error": "Service Unavailable",
       "message": "El servicio de Habitaciones (gRPC) no responde. La solicitud no pudo confirmarse y se marcó para reparación.",
       "reserva_id": 2
     }
   }
   ```

   *(La reserva no se pierde ni genera error 500 no controlado; queda en estado `reparacion` en PostgreSQL para posterior resolución).*

3. **Restaura el servicio gRPC:**

   ```bash
   docker compose start habitaciones-grpc
   ```

4. **Ejecutar la Cascada de Reconciliación y Compensación (`POST /v1/reservas/{id}/resolver`):**

   ```powershell
   Invoke-RestMethod -Uri "http://localhost/v1/reservas/2/resolver" -Method Post -Headers $headers
   ```

   *Respuesta esperada:* La cascada consulta por gRPC a Habitaciones (`ConsultarAsignacion`). Si la habitación nunca se asignó, elimina la reserva en PostgreSQL; si sí se asignó antes de la caída, ejecuta la acción compensatoria (`LiberarHabitacion`) y pasa el estado a `cancelada`.

---

## 5. Declaración de Integridad y Uso de Asistentes de IA (Sección 6.3)

En cumplimiento con los lineamientos de integridad académica del encargo:

* **Propósito del uso:**
  1. Estructuración del contrato Protocol Buffers ([`habitaciones.proto`](contracts/habitaciones.proto)) y especificación OpenAPI.
  2. Implementación de los stubs y resolución de dependencias de empaquetado para el servidor gRPC y el cliente FastAPI.
  3. Verificación de casos de prueba unitarios para la lógica de intervalos semiabiertos e idempotencia.
* **Verificación realizada por el equipo:**
  * Cada línea de código generada fue revisada, ejecutada y validada mediante suites automatizadas de pruebas en pytest (`test_mock_habitacion.py`) y llamadas en vivo de integración (`test_cliente_grpc.py`).
  * Se comprobó empíricamente la resiliencia y el comportamiento del modo de falla (T7) deteniendo y reanudando contenedores Docker en vivo.
