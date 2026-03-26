# Voz Segura IA

Repositorio del proyecto "Voz-Segura-IA" — un asistente conversacional para orientar a víctimas de violencia política contra las mujeres (VPcMRG) y guiar el proceso de generación de un formato de denuncia.

## Qué es

Voz Segura IA es una aplicación basada en Flask que combina técnicas de procesamiento de lenguaje, embeddings y búsqueda semántica (FAISS) para:

- Orientar a usuarias/os sobre sus derechos y el proceso de denuncia.
- Guiar el llenado de un formato de denuncia paso a paso, generando un PDF final.
- Ofrecer búsquedas en documentos legales (PDFs) cargados en la carpeta `static/pdfs`.
- Responder por texto y (opcionalmente) generar audio de la respuesta.

El asistente está pensado para trabajar con documentación legal (PDFs) que el equipo agregue al proyecto para mejorar la precisión de las respuestas.

## Contenido del repositorio

- `app.py` - Aplicación Flask principal y endpoints.
- `formato_denuncia.py` - Generador del PDF de la denuncia.
- `prompt.py` - Prompt/sistema para el LLM.
- `funciones_auxiliares.py` - Utilidades (text-to-speech, validaciones, etc.).
- `requirements.txt` - Dependencias Python.
- `static/pdfs/` - Carpeta donde colocar PDFs legales para indexar.
- `faiss_index/` - Índice FAISS (se genera al ejecutar por primera vez).

## Requisitos

- Python 3.10+ (se probó con 3.12 en el entorno local)
- Dependencias en `requirements.txt`.
- Variables de entorno (ver sección siguiente).

## Variables de entorno

Crea un archivo `.env` en la raíz o exporta las variables en tu entorno:

- `OPENAI_API_KEY` - API Key para OpenAI (si se usan modelos OpenAI).
- `SECRET_KEY` - Clave secreta de Flask para sesiones.

Ejemplo mínimo de `.env`:

OPENAI_API_KEY=tu_api_key_aqui
SECRET_KEY=una_clave_larga_y_secreta

## Instalación y ejecución (local)

1. Crear y activar un virtualenv:

    python -m venv .venv
    source .venv/bin/activate

2. Instalar dependencias:

    pip install -r requirements.txt

3. Coloca los PDFs que quieras indexar en `static/pdfs/`.

4. Exporta variables de entorno o crea `.env`.

5. Ejecuta la aplicación:

    python app.py

La aplicación levanta una web con la interfaz (ruta `/`) y endpoints JSON para chat.

## Endpoints principales

- `GET /` - UI principal.
- `POST /chat` - Endpoint para enviar mensajes (JSON: `{ "message": "..." }`).
- `POST /reload_index` - Fuerza regenerar el índice FAISS (útil al añadir PDFs).
- `GET /download_form` - Descargar formato vacío de denuncia.

Consulta `app.py` para detalles adicionales y más endpoints.

## Ejemplos rápidos

Usa el ejemplo en `examples/chat_example.md` para ver un `curl` básico contra `/chat`.

## Buenas prácticas

- No subas claves secretas al repositorio.
- Añade PDFs en `static/pdfs` relevantes y usa `/reload_index` después de agregarlos.
- Revisa `prompt.py` si deseas adaptar el comportamiento del asistente.

## Contribuir

Lee `CONTRIBUTING.md` para saber cómo colaborar. Se agradecen correcciones, mejoras en documentación y ejemplos reales de interacción (anonimizados).

## Licencia

Este repositorio incluye un archivo `LICENSE` (MIT) por defecto. Revisa y cambia si prefieres otra licencia.

---

Si quieres, puedo:

- Crear issues y un primer commit con estos archivos.
- Ayudarte a crear un flujo de CI básico.

Dime qué prefieres que haga a continuación.
