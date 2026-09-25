from app import schema

# Descripciones reutilizables para OpenAPI.
# Estos diccionarios documentan las respuestas; los handlers las producen.

ERROR_401 = {
    "model": schema.ErrorHTTPResponse,
    "description": "API Key ausente o inválida.",
    "headers": {
        "WWW-Authenticate": {
            "description": "Esquema de autenticación solicitado.",
            "schema": {"type": "string", "enum": ["APIKey"]},
        }
    },
}

ERROR_BD_503 = {
    "model": schema.ErrorResponse,
    "description": "No se pudo completar la operación en la base de datos.",
}

ERROR_RESERVA_404 = {
    "model": schema.ErrorResponse,
    "description": "La reserva solicitada no existe.",
}

ERROR_ESTADO_409 = {
    "model": schema.ErrorResponse,
    "description": "El estado de la reserva impide realizar la operación.",
}

ERROR_OPERACION_503 = {
    "model": schema.ErrorResponse,
    "description": (
        "Fallo de persistencia o resultado incierto de la operación. "
        "Si el tipo es ReservaIncierta, se incluye reserva_id. "
        "Esta respuesta no garantiza que la operación remota no haya ocurrido."
    ),
}

ERROR_DATOS_422 = {
    "model": schema.ErrorValidacionResponse | schema.ErrorResponse,
    "description": (
        "Datos inválidos. Los errores de validación de FastAPI usan detail; "
        "los errores de negocio, como un intervalo inválido, usan error."
    ),
}

RESPUESTAS_BD = {
    401: ERROR_401,
    503: ERROR_BD_503,
}
