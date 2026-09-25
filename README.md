# Integración de Reservas y Habitaciones  — Cadena Hotelera Costanera (Forma H)

Solución de integración de sistemas desarrollada para el **Encargo de Unidad 1** de la asignatura *Integración de Sistemas* (Ingeniería Civil Informática, Universidad de Concepción).

---

## Organizacion


```
Cliente -> REST /v1 (reservas-api) -> PostgreSQL (reservas-bd)
                    |
                    +-> gRPC (habitaciones-grpc) -> SQLite
```

* **Servicio de Reservas (API REST Pública - `/v1`):** Punto de entrada expuesto hacia el exterior. Administra huéspedes y estadías, persistiendo en su propia base de datos PostgreSQL.
* **Servicio de Habitaciones (Microservicio Interno gRPC):** Fuente de verdad sobre el inventario y disponibilidad de habitaciones por fecha. Utiliza SQLite y expone un contrato binario tipado en el puerto `50051`.

Ningún servicio accede a la base de datos del otro; toda consulta o bloqueo se orquesta mediante contratos formales.

| Carpeta o archivo | Contenido |
| --- | --- |
| `reservas/` | API FastAPI, cliente gRPC y persistencia de reservas |
| `habitaciones/` | Servidor gRPC, persistencia de habitaciones y cliente administrativo |
| `contracts/openapi.yaml` | Contrato REST versionado |
| `contracts/habitaciones.proto` | Contrato gRPC, paquete `hotel.habitaciones.v1` |
| `compose.yaml` | Servicios y volúmenes de Docker |
| `decisiones.md` | Registro de decisiones de diseño |

## Setup

### Requisitos Previos

* Docker y Docker Compose instalados.

Si todavía no existe `.env` crearlo desde el ejemplo:

```bash
cp .env.example .env
```

(Compose utiliza `.env`, no `.env.example`. Revisar `RESERVAS_DB_USER`, `RESERVAS_DB_PASSWORD`, `RESERVAS_DB_NAME`, `RESERVAS_DB_URL` y `API_KEY`. La URL debe contener las credenciales reales y usar `reservas-bd` como servidor dentro de Docker. Las credenciales del ejemplo son para desarrollo local. Cambiar estas variables no modifica las credenciales de una base PostgreSQL previamente inicializada en el volumen.)

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=30 reservas-api
```

Se esperan tres servicios activos: `reservas-api` en el puerto 80, `habitaciones-grpc` en 50051 y `reservas-bd` en 5432. PostgreSQL debe aparecer como `healthy`. La API debe completar su arranque. Después de modificar código, repetir el comando con `--build` para incorporarlo a los contenedores.

Los datos se guardan en los volúmenes `reservas-db-data` y `habitaciones-data`. `docker compose down` detiene el sistema conservándolos; agregar `-v` los elimina.


## Ejecucion

Puedes probar todo el sistema paso a paso siguiendo esta guía:

### Preparar habitaciones

El servicio inicia sin habitaciones en una base nueva. El cliente administrativo registra un catálogo de demostración a través de gRPC:

```bash
# 1. Sembrar un catálogo de habitaciones de prueba vía gRPC:
python habitaciones/admin_client.py localhost:50051

# 2. Consultar el inventario de habitaciones registradas:
python habitaciones/admin_client.py localhost:50051 listar

# 3. Registrar una nueva habitación personalizada vía gRPC:
# Uso: python habitaciones/admin_client.py <host> crear <numero> <tipo> <precio_noche>
python habitaciones/admin_client.py localhost:50051 crear 401 Penthouse 250000
```

El número de habitación es único. Volver a ejecutar la carga informa cuáles ya existen. Usar los IDs devueltos por el servicio, sin asumir que corresponden a los números de habitación.

---

### API Rest

Abrir [Swagger UI](http://localhost/docs), seleccionar **Authorize** e ingresar el valor de `API_KEY` configurado en `.env`. Todas las operaciones bajo `/v1` requieren la cabecera `X-API-Key`. La raíz `/` y la documentación son públicas. La raíz identifica la aplicación; no comprueba la salud de todas sus dependencias.

| Método | Ruta | Operación |
| --- | --- | --- |
| POST / GET | `/v1/huespedes` | Crear / listar huéspedes |
| GET | `/v1/huespedes/{huesped_id}` | Consultar un huésped |
| POST / GET | `/v1/reservas` | Crear / listar reservas |
| GET | `/v1/reservas/{reserva_id}` | Consultar una reserva |
| DELETE | `/v1/reservas/{reserva_id}` | Cancelar una reserva y liberar su asignación |
| POST | `/v1/reservas/{reserva_id}/resolver` | Resolver una operación pendiente o incierta |
| GET | `/v1/disponibilidad` | Consultar habitaciones libres en un intervalo |

El archivo `contracts/openapi.yaml` detalla respuestas y errores. Swagger UI y `/openapi.json` se generan a partir de las rutas de FastAPI; las ampliaciones descriptivas del YAML no se cargan automáticamente en Swagger. Al cambiar la API hay que revisar ambos contratos.


---

### Flujo Completo 

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

### Fallos y Resoluciones

Con un huésped existente, detener Habitaciones:

```bash
docker compose stop habitaciones-grpc
```

Intentar crear una nueva reserva:

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

El cliente gRPC tiene un timeout de 2 segundos por llamada; una conexión rechazada puede fallar antes. Ante un fallo de comunicación, la API intenta marcar la reserva como `reparacion` y responde 503. Por ejemplo, para una reserva cuyo ID sea 42:

```json
{
  "error": {
    "tipo": "ReservaIncierta",
    "mensaje": "No se conoce el resultado de la reserva 42",
    "reserva_id": 42
  }
}
```


Restaurar el servicio y ejecutar `POST /v1/reservas/{reserva_id}/resolver` con el ID recibido:

```bash
docker compose start habitaciones-grpc
```

```powershell
Invoke-RestMethod -Uri "http://localhost/v1/reservas/2/resolver" -Method Post -Headers $headers
  ```

La resolución consulta la asignación remota y la libera si corresponde. Si la reserva local todavía no tiene `habitacion_id`, elimina el registro local, incluso si antes necesitó liberar una asignación remota. Si ya tiene `habitacion_id`, termina en estado `cancelada`. Una reserva confirmada produce 409; una ya cancelada se devuelve sin modificar. La resolución es manual: no existe un proceso automático que revise las reservas en reparación.

Los errores de negocio usan `{"error":{"tipo":"...","mensaje":"..."}}`. La autenticación y el correo duplicado usan `{"detail":"..."}`; la validación de FastAPI usa `{"detail":[...]}`. El contrato describe estas diferencias.

## Pruebas y estado de verificación

Las pruebas disponibles son:

- `reservas/test_mock_habitacion.py`: comportamiento del doble de prueba en memoria, con asignaciones, intervalos, liberación y fallos simulados. No verifica por sí solo el servicio gRPC real.
- `reservas/test_e2e_cascadas.py`: pruebas contra la API en `localhost`. Requieren servicios activos y datos preparados. Actualmente contienen supuestos sobre IDs y una comprobación del formato de error que necesita actualizarse; no deben presentarse como evidencia de que todos los escenarios pasan.

Para ejecutar las pruebas del mock en el entorno local:

```bash
python -m pip install pytest
cd reservas
python -m pytest test_mock_habitacion.py -q
```

Para trabajar en las pruebas E2E se necesita además `requests`. Su ejecución modifica datos del sistema de demostración. La experimentación medida se está desarrollando por separado; esta guía no presenta resultados experimentales ni atribuye mejoras de rendimiento sin mediciones.
---


## Uso de IA

Se utilizaron GPT-6 Sol y GPT-6 Astra para generar propuestas de código a partir de las ideas y decisiones planteadas durante el desarrollo. En ese flujo, el código propuesto se revisó y se incorporó manualmente mediante copia y pegado, en lugar de delegar a un agente la implementación automática del proyecto.

También se utilizó asistencia de IA para revisar el proyecto y actualizar este README y el contrato OpenAPI. Esta revisión documental debe distinguirse del flujo manual usado para incorporar código.

Las verificaciones realizadas incluyen la revisión del código frente a los requisitos, la comprobación del arranque y acceso de la API a PostgreSQL, y pruebas aisladas del comportamiento del endpoint de resolución. Parte de esta comprobación se realizó con asistencia de IA. No se afirma que cada línea haya sido validada ni que toda la suite E2E haya pasado. Las pruebas disponibles y sus límites se describen en la sección anterior.
