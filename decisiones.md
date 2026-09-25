# Registro de Decisiones de Arquitectura e Implementación

Este documento recopila de forma estructurada todas las decisiones de ingeniería, arquitectura, contratos y configuración tomadas por el equipo para el diseño e implementación de la solución de integración. Estas decisiones constituyen la base técnica para la defensa oral y la redacción de los ADRs (Architecture Decision Records) del informe final.

---

## Índice de Decisiones

1. [DEC-01: Patrón de Arquitectura ("REST hacia afuera, gRPC hacia adentro")](#dec-01-patrón-de-arquitectura-rest-hacia-afuera-grpc-hacia-adentro)
2. [DEC-02: Base de Datos por Servicio y Persistencia Políglota (T5)](#dec-02-base-de-datos-por-servicio-y-persistencia-políglota-t5)
3. [DEC-03: Semántica de Fechas e Intervalo Semiabierto para Estadías](#dec-03-semántica-de-fechas-e-intervalo-semiabierto-para-estadías)
4. [DEC-04: Lógica de Asignación de Habitaciones (Estrategia Híbrida)](#dec-04-lógica-de-asignación-de-habitaciones-estrategia-híbrida)
5. [DEC-05: Idempotencia en la Asignación gRPC mediante Clave de Correlación](#dec-05-idempotencia-en-la-asignación-grpc-mediante-clave-de-correlación)
6. [DEC-06: Gestión de Catálogo de Habitaciones Exclusiva vía gRPC](#dec-06-gestión-de-catálogo-de-habitaciones-exclusiva-vía-grpc)
7. [DEC-07: Mecanismo de Autenticación de la API REST (T6)](#dec-07-mecanismo-de-autenticación-de-la-api-rest-t6)
8. [DEC-08: Manejo de Resiliencia, Timeouts y Modo de Falla (T7 / D4)](#dec-08-manejo-de-resiliencia-timeouts-y-modo-de-falla-t7--d4)
9. [DEC-09: Independencia y Ubicación de los Stubs Compilados de Protobuf](#dec-09-independencia-y-ubicación-de-los-stubs-compilados-de-protobuf)
10. [DEC-10: Estrategia de Dockerización y Orquestación con Compose (T1)](#dec-10-estrategia-de-dockerización-y-orquestación-con-compose-t1)

---

### DEC-01: Patrón de Arquitectura ("REST hacia afuera, gRPC hacia adentro")

* **Contexto:** Se requiere integrar dos sistemas independientes: Reservas (atención a clientes y huéspedes) y Habitaciones (administración interna de inventario de alta concurrencia).
* **Alternativas consideradas:**
  * *Opción A:* REST/JSON en ambos servicios.
  * *Opción B:* gRPC en ambos servicios.
  * *Opción C:* Patrón híbrido: REST/JSON para clientes externos y gRPC/Protobuf para la comunicación inter-servicios.
* **Decisión tomada:** **Opción C (REST hacia afuera, gRPC hacia adentro)**.
* **Justificación:**
  * **Hacia afuera:** REST/JSON sobre HTTP/1.1 provee compatibilidad universal con navegadores web, clientes móviles, herramientas de prueba (Swagger UI, Postman) y fácil depuración por inspección de texto plano.
  * **Hacia adentro:** gRPC sobre HTTP/2 ofrece multiplexación en una sola conexión TCP, compresión de cabeceras (HPACK), contratos estrictamente tipados y serialización binaria que reduce drásticamente el uso de CPU y el ancho de banda ante consultas de disponibilidad de alto volumen.
* **Costo aceptado:** Mayor complejidad al mantener dos tecnologías de comunicación y dos especificaciones de contrato (`openapi.yaml` y `habitaciones.proto`).

---

### DEC-02: Base de Datos por Servicio y Persistencia Políglota (T5)

* **Contexto:** El requisito técnico obligatorio T5 exige que ningún servicio acceda al almacén de datos del otro de forma directa.
* **Alternativas consideradas:**
  * *Opción A:* Dos bases de datos independientes dentro de un mismo clúster PostgreSQL.
  * *Opción B:* Persistencia políglota: PostgreSQL para Reservas y SQLite embebido en volumen persistente para Habitaciones.
* **Decisión tomada:** **Opción B (Persistencia Políglota)**.
  * `reservas-bd`: **PostgreSQL 16** (ideal para relaciones relacionales de huéspedes, historial de reservas y concurrencia transaccional pesada).
  * `habitaciones`: **SQLite** en `/data/habitaciones.db` (motor ligero, cero mantenimiento de servidor de base de datos adicional, altísima velocidad de lectura local de inventario).
* **Justificación:** Aísla de raíz la frontera de datos. Evita la tentación de realizar *joins* entre esquemas a nivel de base de datos y reduce el consumo de memoria RAM de la solución en Docker.
* **Costo aceptado:** Se requiere gestionar volúmenes de respaldo independientes (`reservas-db-data` y `habitaciones-data`).

---

### DEC-03: Semántica de Fechas e Intervalo Semiabierto para Estadías

* **Contexto:** En el dominio de hotelería, las estadías se computan por **noches ocupadas**. Un huésped que sale el día 5 de noviembre desocupa la habitación al mediodía, permitiendo que un nuevo huésped ingrese esa misma tarde.
* **Alternativas consideradas:**
  * *Opción A:* Intervalo cerrado $[inicio, fin]$ (marcaría el día de salida como ocupado, impidiendo el check-in de nuevos huéspedes el mismo día).
  * *Opción B:* Intervalo semiabierto $[inicio, fin)$ donde la fecha de inicio es inclusiva y la de fin es exclusiva.
* **Decisión tomada:** **Opción B (Intervalo semiabierto $[inicio, fin)$)**.
* **Justificación:** La condición de solapamiento en el código:
  $$\text{inicio} < \text{asignación.fin} \quad \text{y} \quad \text{asignación.inicio} < \text{fin}$$
  permite matemáticamente que si una reserva termina el día 5 y otra inicia el día 5, no exista conflicto.
* **Costo aceptado:** La API debe validar explícitamente que $\text{fecha\_fin} > \text{fecha\_inicio}$ (una estadía de 0 noches o fechas invertidas se rechaza con error 400).

---

### DEC-04: Lógica de Asignación de Habitaciones (Estrategia Híbrida)

* **Contexto:** Al momento de generar una reserva, un huésped puede desear una habitación específica (ej. Suite Presidencial 302) o simplemente solicitar cualquier habitación disponible para sus fechas.
* **Alternativas consideradas:**
  * *Opción A:* Asignación exclusivamente manual (el cliente siempre debe proveer el `habitacion_id`).
  * *Opción B:* Asignación exclusivamente automática (el sistema siempre elige por el cliente).
  * *Opción C:* Estrategia híbrida opcional.
* **Decisión tomada:** **Opción C (Estrategia Híbrida)**.
* **Justificación:** En `AsignarHabitacionRequest`, el campo `optional int32 habitacion_id` permite que si el cliente no lo especifica (o es 0), el servicio de Habitaciones busque y asigne automáticamente la primera habitación libre. Si se envía un ID específico, el servicio valida si dicha habitación está desocupada para asignarla, o de lo contrario devuelve rechazo `NO_DISPONIBLE`.
* **Costo aceptado:** El servicio gRPC debe contemplar ambas rutas de ejecución en su capa de lógica (`crud.asignar_habitacion`).

---

### DEC-05: Idempotencia en la Asignación gRPC mediante Clave de Correlación

* **Contexto:** Ante fallos de red intermitentes, una petición de asignación puede persistir en Habitaciones pero la respuesta puede perderse en el camino hacia Reservas. Un reintento ingenuo provocaría que Habitaciones rechace la reserva por "habitación ocupada por sí misma".
* **Alternativas consideradas:**
  * *Opción A:* Reintentar sin identificador único (arriesga falsos rechazos por sobreventa).
  * *Opción B:* Uso del `reserva_id` como clave de correlación e idempotencia.
* **Decisión tomada:** **Opción B (Idempotencia por `reserva_id`)**.
* **Justificación:** Cuando Habitaciones recibe una solicitud de asignación:
  1. Verifica si ya existe una asignación activa con ese `reserva_id`.
  2. Si existe para las mismas fechas, devuelve inmediatamente el estado `YA_ASIGNADA` y el `habitacion_id` correspondiente sin error ni duplicar el registro.
  3. Si existe para fechas distintas, alerta de un conflicto de datos (`DATOS_INVALIDOS`).
* **Verificación End-to-End (E2E):** Probado y validado de extremo a extremo comunicando la API REST de Reservas (PostgreSQL) con el microservicio Habitaciones (SQLite) a través de Docker. Ante reintentos con el mismo identificador, no se generan duplicados ni bloqueos inconsistentes.
* **Costo aceptado:** Requiere que la reserva sea registrada previamente en estado `PENDIENTE` en Reservas para obtener el ID antes de contactar a Habitaciones.

---

### DEC-06: Gestión de Catálogo de Habitaciones Exclusiva vía gRPC

* **Contexto:** El servicio de Habitaciones inicia con su base de datos SQLite vacía y se requiere registrar las habitaciones físicas del hotel.
* **Alternativas consideradas:**
  * *Opción A:* Insertar datos directamente en el archivo SQLite mediante scripts fuera de línea (*backdoor* a la BD).
  * *Opción B:* Exponer los métodos `CrearHabitacion` y `ListarHabitaciones` en el contrato gRPC y proveer un cliente administrativo ([`admin_client.py`](habitaciones/admin_client.py)).
* **Decisión tomada:** **Opción B (Gestión exclusiva mediante contrato gRPC)**.
* **Justificación:** Respeta estrictamente los límites del microservicio (*encapsulation*). Nadie manipula la base de datos de Habitaciones por fuera; todo pasa por validaciones de negocio y tipos en Protobuf.
* **Costo aceptado:** Se debe proveer una herramienta o script CLI que consuma el stub gRPC para sembrar o administrar el catálogo.

---

### DEC-07: Mecanismo de Autenticación de la API REST (T6)

* **Contexto:** El requisito técnico obligatorio T6 exige un mecanismo de autenticación justificado y reflejado en el contrato OpenAPI.
* **Alternativas consideradas:**
  * *Opción A:* HTTP Basic Auth (usuario y contraseña en Base64).
  * *Opción B:* Bearer Token JWT (requiere firma criptográfica, expiración y servidor de emisión).
  * *Opción C:* API Key mediante encabezado HTTP (`X-API-Key`).
* **Decisión tomada:** **Opción C (API Key vía `X-API-Key: hotel-secret-key-2026`)**.
* **Justificación:**
  * Es el estándar más utilizado en integraciones B2B y portales organizacionales donde la API es consumida por clientes identificados.
  * Simple de justificar, no agrega la sobrecarga de un proveedor de identidad OAuth2/JWT para el alcance de este encargo.
  * Si la cabecera falta o es incorrecta, devuelve de forma inmediata `HTTP 401 Unauthorized` con cuerpo JSON estandarizado.
  * La documentación Swagger UI ([`/docs`](http://localhost/docs)) se dejó pública para permitir la inspección interactiva y evaluación, protegiendo todas las operaciones de datos bajo `/v1`.
* **Costo aceptado:** La clave debe protegerse en variables de entorno (`API_KEY`) y no en el código fuente.

---

### DEC-08: Manejo de Resiliencia, Timeouts, Negación de Servicio y Cascadas de Compensación / Rollback (T7 / D4)

* **Contexto:** Si el servicio interno de Habitaciones rechaza una petición (por no disponibilidad) o se cae/sufre negación de servicio (timeout o caída de red), el sistema debe garantizar consistencia eventual mediante **cascadas de volver atrás (rollback y compensación Saga)**, sin dejar registros huérfanos ni congelar la API.
* **Alternativas consideradas:**
  * *Opción A:* Espera infinita sin timeout y sin reversión (deja transacciones a medias y tablas sucias).
  * *Opción B:* Protocolo de Dos Fases (2PC) tradicional
  * *Opción C:* Timeout estricto con **Cascadas de Rollback y Compensación Saga**:
* **Decisión tomada:** **Opción C (Cascadas de Rollback y Compensación Saga con Timeout de 2.0s)**.
* **Mecanismos de Cascada Implementados:**
  1. **Cascada de Rollback Inmediata por Negación de Disponibilidad:**
     * Cuando un cliente intenta reservar fechas ocupadas o habitaciones inexistentes, Habitaciones responde `NO_DISPONIBLE` por gRPC.
     * En respuesta, Reservas ejecuta inmediatamente la cascada de reversión: elimina el registro temporal `PENDIENTE` de PostgreSQL (`crud.delete_reserva_by_id`) y retorna `HTTP 409 Conflict: "No hay habitación para toda la estadía"`.
     * **Resultado comprobado:** Cero reservas huérfanas en la base de datos de Reservas ante rechazo.
  2. **Cascada de Transición ante Negación de Servicio (Caída de red / Timeout):**
     * En [reservas/app/grpc.py](reservas/app/grpc.py), toda llamada gRPC tiene un límite de 2.0s (`timeout=2.0`).
     * Si ocurre `DEADLINE_EXCEEDED` o `UNAVAILABLE` (servicio de Habitaciones apagado), la API no crashea ni devuelve 500 no controlado; pasa la reserva al estado transaccional **`REPARACION`** y responde al cliente `HTTP 503 Service Unavailable` con cuerpo JSON descriptivo y el ID de la reserva.
  3. **Cascada de Reconciliación y Compensación (`resolver_reserva`):**
     * Para volver atrás o reparar de forma segura una reserva en estado `REPARACION` una vez que la red se reanuda, se expone el endpoint administrativo `POST /v1/reservas/{id}/resolver`.
     * La cascada consulta a Habitaciones vía gRPC (`ConsultarAsignacion`):
       * *Si la habitación nunca se asignó:* la cascada elimina la reserva localmente de PostgreSQL.
       * *Si la habitación sí alcanzó a asignarse antes del corte:* la cascada ejecuta la **acción compensatoria** llamando a `LiberarHabitacion(reserva_id)` en gRPC para no dejar habitaciones bloqueadas en el hotel, y actualiza la reserva en PostgreSQL a `CANCELADA`.
* **Validación End-to-End Real:**
  * Se probó el ciclo completo con contenedores en ejecución en [test_e2e_cascadas.py](reservas/test_e2e_cascadas.py), verificando la eliminación de registros sucios en PostgreSQL y la liberación en SQLite ante rechazos y caídas simuladas.
* **Costo aceptado:** Requiere el endpoint de resolución administrativa `POST /v1/reservas/{id}/resolver` para reservas en estado dudoso.

---

### DEC-09: Independencia y Ubicación de los Stubs Compilados de Protobuf

* **Contexto:** Ambos servicios necesitan los módulos Python generados (`habitaciones_pb2.py` y `habitaciones_pb2_grpc.py`).
* **Alternativas consideradas:**
  * *Opción A:* Una carpeta compartida `contracts/gen` montada como volumen común en Docker.
  * *Opción B:* Compilar y ubicar los stubs dentro del árbol de cada servicio (`habitaciones/app/protos` y `reservas/app/protos`).
* **Decisión tomada:** **Opción B (Stubs independientes por servicio)**.
* **Justificación:** Garantiza la **autonomía de despliegue**. Cada contenedor Docker se empaqueta con sus propios archivos fuente sin acoplamientos en tiempo de compilación con el sistema de archivos del host o volúmenes compartidos.
* **Costo aceptado:** Si el archivo `.proto` se modifica, debe re-compilarse en ambas carpetas.

---

### DEC-10: Estrategia de Dockerización y Orquestación con Compose (T1)

* **Contexto:** El requisito T1 exige que todo el ecosistema levante de forma limpia con un único `docker compose up`.
* **Alternativas consideradas:**
  * *Opción A:* Uso de `postgres:latest` sin comprobación de salud.
  * *Opción B:* Uso de imágenes estables (`postgres:16-alpine`), `healthcheck` en la base de datos y condiciones `depends_on: { condition: service_healthy }`.
* **Decisión tomada:** **Opción B**.
* **Justificación:**
  * Evita condiciones de carrera (*race conditions*): `reservas-api` no intenta conectarse a PostgreSQL hasta que el motor esté listo para recibir consultas (`pg_isready`).
  * Utiliza volúmenes con nombre (`reservas-db-data` y `habitaciones-data`) para garantizar la persistencia de datos tras reinicios de contenedores.
* **Costo aceptado:** Requiere configurar bloques de `healthcheck` explícitos en el archivo [compose.yaml](compose.yaml).
