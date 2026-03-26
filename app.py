from flask import Flask, request, render_template, jsonify, session, send_file
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from sentence_transformers import SentenceTransformer
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from formato_denuncia import procesar_denuncia
from werkzeug.utils import secure_filename
from funciones_auxiliares import *
from flask_session import Session
from prompt import SYSTEM_PROMPT
from dotenv import load_dotenv
from openai import OpenAI
import threading
import glob
import markdown
import os

# Cargar variables de entorno
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
db_lock = threading.Lock()  # Evita condiciones de carrera en multi-threading
db = None  # Global para almacenar FAISS

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# Carpeta donde están los documentos PDF
PDF_FOLDER = "static/pdfs"
AUDIO_FOLDER = "uploads/audio"
INDEX_PATH = "faiss_index"  # Nombre del archivo donde guardaremos el índice
os.makedirs(AUDIO_FOLDER, exist_ok=True)  # Crear la carpeta si no existe

app.config["SESSION_TYPE"] = "filesystem"  # Tipo de sesión en archivos
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_FILE_DIR"] = "./flask_sessions"

Session(app)  # Ahora se inicializa correctamente

# Cargar modelo de embeddings
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

respuestas_proceder = ["proceder", "iniciar", "vamos", "sí", "si", "ok", "1"]
respuestas_no = ["no", "2", "cancelar", "omitir"]

def get_db():
    global db
    with db_lock:  # Garantiza que solo un hilo cargue el índice
        if db is None:
            db = load_or_create_index()
        return db

# Función para cargar y procesar documentos PDF
def load_pdfs():
    documents = []
    if not os.path.exists(PDF_FOLDER):
        print("❌ Carpeta de PDFs no encontrada.")
        return []

    for filename in os.listdir(PDF_FOLDER):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(PDF_FOLDER, filename)
            loader = PyPDFLoader(pdf_path)
            docs = loader.load()
            if docs:
                print(f"📄 Cargado {filename} con {len(docs)} páginas.")
            documents.extend(docs)

    return documents

def load_or_create_index():
    """Carga el índice FAISS desde disco si existe, de lo contrario lo crea."""
    index_files = glob.glob(f"{INDEX_PATH}*")  # Verificar si hay archivos FAISS

    if index_files:
        print("🔄 Cargando índice FAISS desde disco...")
        try:
            db_instance = FAISS.load_local(INDEX_PATH, OpenAIEmbeddings(), allow_dangerous_deserialization=True)
            if db_instance is not None:
                return db_instance
        except Exception as e:
            print(f"⚠️ Error al cargar índice FAISS: {str(e)}. Se intentará regenerar.")

    print("📌 Generando nuevo índice FAISS...")

    #Cargar los PDFs antes de intentar dividirlos
    pdf_documents = load_pdfs()
    if not pdf_documents:
        print("❌ No hay documentos PDF disponibles. No se generará FAISS.")
        return None  # Evita errores si no hay documentos

    # 📝 Dividir documentos solo si hay documentos PDF cargados
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    split_docs = text_splitter.split_documents(pdf_documents)

    print(f"📌 Se generaron {len(split_docs)} fragmentos de texto para indexar.")

    # 🔹 Crear FAISS solo si hay fragmentos de texto
    if split_docs:
        db_instance = FAISS.from_documents(split_docs, OpenAIEmbeddings())
        db_instance.save_local(INDEX_PATH)
        print(f"✅ Índice FAISS guardado en {INDEX_PATH}")
        return db_instance
    else:
        print("❌ No se pudieron generar fragmentos de texto. Verifica los documentos PDF.")
        return None

db = load_or_create_index()

# Búsqueda en los documentos PDF
def search_in_pdfs(query, top_k=3):
    db_instance = get_db()
    if db_instance is None:
        print("⚠️ No hay documentos indexados aún.")
        return "⚠️ No hay documentos indexados aún."

    try:
        retrieved_docs = db_instance.similarity_search(query, k=top_k)
        retrieved_text = "\n".join([doc.page_content for doc in retrieved_docs])
        print(f"🔍 Búsqueda en FAISS: {retrieved_text[:500]}")
        return retrieved_text
    except Exception as e:
        print(f"❌ Error en búsqueda FAISS: {str(e)}")
        return "⚠️ Error al buscar en los documentos."

@app.route("/reload_index", methods=["POST"])
def reload_index():
    """Permite regenerar el índice FAISS manualmente sin reiniciar Flask"""
    global db
    with db_lock:
        print("♻️ Regenerando índice FAISS...")
        db = load_or_create_index()
    
    return jsonify({"message": "Índice FAISS regenerado correctamente."})

@app.route("/")
def home():
    session.clear()
    return render_template("index.html")

@app.route("/movile")
def movile():
    session.clear()
    return render_template("movil.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json
        user_message = data.get("message", "").strip().lower()
        
        if not user_message:
            return jsonify({"response": "No recibí ningún mensaje. 😕"})

        # Inicializar la conversación en session si no existe
        if "messages" not in session:
            session["messages"] = []

        # -----------------------------------------------------------------------
        # 1) ¿Estamos en proceso de llenar datos de denuncia?
        # -----------------------------------------------------------------------
        if "datos_faltantes" in session and session["datos_faltantes"]:
            datos_faltantes = session["datos_faltantes"]
            datos_usuario = session.get("datos_usuario", {})
            dato_actual = datos_faltantes[0]

            # CANCELAR (misma lógica)
            if user_message.startswith("cancelar"):
                return handle_cancelar_proceso()
            
            # OMITIR (misma lógica)
            if user_message.startswith("omitir"):
                return handle_omitir_dato(dato_actual, datos_faltantes, datos_usuario)

            # -------------------------------------------------------------------
            # Manejo de preguntas/dudas y "continuar"
            # -------------------------------------------------------------------
            # Si detectamos que el usuario tiene dudas/preguntas, respondemos sin avanzar de campo.
            if es_duda(user_message):
                # Llamamos al LLM con un prompt que explique el campo y pregunte si desea continuar
                explanation_prompt = f"""
                {SYSTEM_PROMPT}

                ### Contexto:
                El usuario está llenando un **formato de denuncia** y tiene dudas o quiere más información 
                sobre el siguiente dato: **{dato_actual}**.
                Explícale por qué es importante, dale ejemplos si aplica. 
                Luego, termina la respuesta con una frase para saber si quiere 
                'continuar' o si tiene más dudas, por ejemplo:
                "¿Tienes más dudas o deseas continuar con la denuncia?"
                
                📩 Pregunta del usuario: "{user_message}"
                """

                messages = session["messages"]
                messages.append({"role": "user", "content": user_message})

                completion_exp = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[{"role": "system", "content": explanation_prompt}] + messages,
                    max_tokens=500
                )
                explanation_response = (completion_exp.choices[0].message.content 
                                        if completion_exp.choices else "No se pudo obtener una respuesta clara.")

                # Actualizamos 'messages'
                session["messages"] = messages

                # Devolvemos la explicación; seguimos en el MISMO dato
                return jsonify({"response": markdown.markdown(explanation_response)})

            # Si el usuario dice "continuar", interpretamos que ya no tiene más dudas 
            # y quiere dar el dato. Le pedimos que ingrese el valor (o lo revalidamos).
            continuar_triggers = ["continuar", "avanzar", "seguir", "ok", "listo", "entiendo", "comprendo", "ya entendí", "ya entendi"]
            if any(trigger in user_message for trigger in continuar_triggers):
                # Obtener el campo actual (o el siguiente campo, según tu lógica)
                if "datos_faltantes" in session and session["datos_faltantes"]:
                    siguiente_dato = session["datos_faltantes"][0]
                    texto = (
                            f"Perfecto, continuemos con la denuncia. "
                            f"El siguiente dato que necesito es {siguiente_dato}. "
                            "Por favor, ingrésalo, o escribe 'omitir' si no deseas proporcionarlo, "
                            "o 'cancelar' para detener el proceso."
                        )
                    audio_response_path = text_to_speech(texto)
                    # Simplemente le dices al usuario: "ok, continuemos con ... "
                    return jsonify({
                        "response": markdown.markdown(
                            f"Perfecto, continuemos con la denuncia. "
                            f"El siguiente dato que necesito es **{siguiente_dato}**. "
                            "Por favor, ingrésalo, o escribe 'omitir' si no deseas proporcionarlo, "
                            "o 'cancelar' para detener el proceso."
                        ),
                        "audio_response": audio_response_path
                    })
                else:
                    texto = (
                            "No hay más datos pendientes. Parece que la denuncia está casi completa. "
                            "Si deseas revisarla o generar el PDF, avísame."
                            )
                    audio_response_path = text_to_speech(texto)
                    return jsonify({
                        "response": (
                            "No hay más datos pendientes. Parece que la denuncia está casi completa. "
                            "Si deseas revisarla o generar el PDF, avísame."
                        ),
                        "audio_response": audio_response_path
                    })
                    
            # --------------------------------
            #  1) MEDIDAS CAUTELARES
            # --------------------------------
            if dato_actual == "medidas_cautelares":
                # Si no existe la lista en datos_usuario, se crea
                if "medidas_cautelares_lista" not in datos_usuario:
                    datos_usuario["medidas_cautelares_lista"] = []

                # Siempre mostrar la lista de opciones antes de esperar la respuesta del usuario
                opciones_str = "\n".join(f"{i+1}. {op}" for i, op in enumerate(MEDIDAS_CAUTELARES_OPCIONES))
                
                # Si el usuario no ha ingresado nada aún, se le muestran las opciones
                if not session.get("pidiendo_medidas_cautelares", False):
                    session["pidiendo_medidas_cautelares"] = True
                    texto = f"Estas son las medidas cautelares disponibles: {opciones_str}. Para seleccionar, escribe los números separados por comas (ej: '1,3'). Escribe 'otra' para agregar una medida no listada. Cuando termines, escribe 'terminar'."                    
                    audio_response_path = text_to_speech(texto)
                    return jsonify({
                        "response": (
                            "Estas son las medidas cautelares disponibles:\n\n"
                            f"{opciones_str}\n\n"
                            "Para seleccionar, escribe los números separados por comas (ej: '1,3'). "
                            "Escribe 'otra' para agregar una medida no listada. "
                            "Cuando termines, escribe 'terminar'."
                        ),
                        "audio_response": audio_response_path
                    })
                # Manejo de 'terminar' para medidas cautelares
                if user_message == "terminar":
                    # Verificar si se han seleccionado medidas cautelares
                    if not datos_usuario.get("medidas_cautelares_lista"):
                        datos_usuario["medidas_cautelares"] = "_________________________"
                    else:
                        texto_medidas = "\n".join(f"- {m}" for m in datos_usuario["medidas_cautelares_lista"])
                        datos_usuario["medidas_cautelares"] = texto_medidas

                    # Guardar en sesión antes de continuar
                    session["datos_usuario"] = datos_usuario

                    # Remover 'pidiendo_medidas_cautelares' de la sesión
                    session.pop("pidiendo_medidas_cautelares", None)

                    # Avanzar al siguiente dato
                    if session.get("datos_faltantes"):
                        session["datos_faltantes"] = session["datos_faltantes"][1:]
                    
                    # Verificar si aún hay datos faltantes
                    if session["datos_faltantes"]:
                        siguiente_dato = session["datos_faltantes"][0]

                        # Definir opciones de medidas de protección
                        opciones_str = "\n".join(f"{i+1}. {op}" for i, op in enumerate(MEDIDAS_PROTECCION_OPCIONES))

                        # Ahora activar la petición de medidas de protección
                        session["pidiendo_medidas_proteccion"] = True  # <--- NUEVA VARIABLE PARA CONTROLAR EL FLUJO
                        texto = f"Se han registrado tus medidas cautelares. Ahora, selecciona las medidas de protección que solicitas para proteger tus derechos. Estas son las medidas de protección disponibles: {opciones_str}. Para seleccionar, escribe los números separados por comas (ej: '1,3'). Escribe 'otra' para agregar una medida no listada. Cuando termines, escribe 'terminar'."                    
                        audio_response_path = text_to_speech(texto)
                        return jsonify({
                            "response": markdown.markdown(
                                "✅ Se han registrado tus medidas cautelares.\n\n"
                                "Ahora, selecciona las **medidas de protección** que solicitas para proteger tus derechos.\n\n"
                                "Estas son las medidas de protección disponibles:\n\n"
                                f"{opciones_str}\n\n"
                                "Para seleccionar, escribe los números separados por comas (ej: '1,3'). "
                                "Escribe 'otra' para agregar una medida no listada. "
                                "Cuando termines, escribe 'terminar'."
                            ),
                            "audio_response": audio_response_path
                        })

                    else:
                        # No hay más campos, generar la denuncia
                        try:
                            resultado = procesar_denuncia(datos_usuario)
                            if isinstance(resultado, dict) and "error" in resultado:
                                session["datos_faltantes"] = resultado["faltantes"]
                                return jsonify({
                                    "response": (f"⚠️ Faltan datos: {', '.join(resultado['faltantes'])}. "
                                                "Por favor, ingrésalos para continuar."),
                                    "audio_response": audio_response_path
                                })
                            session["pdf_path"] = resultado
                            session.pop("datos_faltantes", None)
                            session.pop("datos_usuario", None)
                            texto = "La denuncia ha sido generada correctamente. Puedes descargarla en el link que te genere. Este es un formato de denuncia con los datos proporcionados. Puedes revisarlo y editarlo si lo deseas. ¡Estoy aquí para ayudarte!"
                            audio_response_path = text_to_speech(texto)
                            return jsonify({
                                "response": (
                                    "✅ La denuncia ha sido generada correctamente. "
                                    "Puedes descargarla aquí: /download_sue\n\n"
                                    "Este es un formato de denuncia con los datos proporcionados. "
                                    "Puedes revisarlo y editarlo si lo deseas. "
                                    "¡Estoy aquí para ayudarte! 😊"
                                ),
                                "audio_response": audio_response_path
                            })
                        except Exception as e:
                            return jsonify({"response": f"❌ Error al generar la denuncia: {str(e)}"}), 500

                # Manejo de 'otra'
                if user_message == "otra":
                    texto = "Escribe la medida cautelar adicional que deseas. Cuando termines, escribe 'terminar'."
                    audio_response_path = text_to_speech(texto)
                    return jsonify({
                        "response": (
                            "Escribe la medida cautelar adicional que deseas. "
                            "Cuando termines, escribe 'terminar'."
                        ),
                        "audio_response": audio_response_path
                    })

                # Interpretar la selección
                selecciones = [s.strip() for s in user_message.split(",")]
                added_something = False

                for sel in selecciones:
                    if sel.isdigit():
                        idx = int(sel) - 1
                        if 0 <= idx < len(MEDIDAS_CAUTELARES_OPCIONES):
                            datos_usuario["medidas_cautelares_lista"].append(MEDIDAS_CAUTELARES_OPCIONES[idx])
                            added_something = True
                    else:
                        # Agregar medidas personalizadas
                        if sel:
                            datos_usuario["medidas_cautelares_lista"].append(sel)
                            added_something = True

                session["datos_usuario"] = datos_usuario
                texto = "Medidas cautelares seleccionadas:\n" + "\n".join(f"- {m}" for m in datos_usuario["medidas_cautelares_lista"]) + "\n\nEscribe más números, 'otra' para añadir otra, o 'terminar' si has terminado con las medidas cautelares."
                audio_response_path = text_to_speech(texto)
                return jsonify({
                    "response": (
                        "Medidas cautelares seleccionadas:\n"
                        + "\n".join(f"- {m}" for m in datos_usuario["medidas_cautelares_lista"])
                        + "\n\nEscribe más números, 'otra' para añadir otra, "
                        "o 'terminar' si has terminado con las medidas cautelares."
                    ),
                    "audio_response": audio_response_path
                })

            # --------------------------------
            #  2) MEDIDAS DE PROTECCIÓN
            # --------------------------------
            if dato_actual == "medidas_proteccion":
                # Si no existe la lista en datos_usuario, se crea
                if "medidas_proteccion_lista" not in datos_usuario:
                    datos_usuario["medidas_proteccion_lista"] = []

                # Siempre mostrar la lista de opciones antes de esperar la respuesta del usuario
                opciones_str = "\n".join(f"{i+1}. {op}" for i, op in enumerate(MEDIDAS_PROTECCION_OPCIONES))

                if not session.get("pidiendo_medidas_proteccion", False):
                    session["pidiendo_medidas_proteccion"] = True
                    texto = f"Estas son las medidas de protección disponibles: {opciones_str}.Para seleccionar, escribe los números separados por comas (ej: '1,3').Escribe 'otra' para agregar una medida no listada. Cuando termines, escribe 'terminar'."
                    audio_response_path = text_to_speech(texto)
                    return jsonify({
                        "response": (
                            "Estas son las medidas de protección disponibles:\n\n"
                            f"{opciones_str}\n\n"
                            "Para seleccionar, escribe los números separados por comas (ej: '1,3'). "
                            "Escribe 'otra' para agregar una medida no listada. "
                            "Cuando termines, escribe 'terminar'."
                        ),
                        "audio_response": audio_response_path
                    })

                # Manejo de 'terminar' para medidas de protección
                if user_message == "terminar":
                    # Verificar si se han seleccionado medidas de protección
                    if not datos_usuario.get("medidas_proteccion_lista"):
                        datos_usuario["medidas_proteccion"] = "_________________________"
                    else:
                        texto_protecciones = "\n".join(f"- {m}" for m in datos_usuario["medidas_proteccion_lista"])
                        datos_usuario["medidas_proteccion"] = texto_protecciones

                    # Guardar en sesión antes de continuar
                    session["datos_usuario"] = datos_usuario

                    # Remover 'pidiendo_medidas_proteccion' de la sesión
                    session.pop("pidiendo_medidas_proteccion", None)

                    # Avanzar al siguiente dato si hay más pendientes
                    if session.get("datos_faltantes"):
                        session["datos_faltantes"] = session["datos_faltantes"][1:]

                    # Verificar si aún hay datos faltantes
                    if session["datos_faltantes"]:
                        siguiente_dato = session["datos_faltantes"][0]
                        texto = f"Se han registrado tus medidas de protección.Ahora necesito {siguiente_dato}.¿Qué tipo de prueba deseas ofrecer? Elige una opción: 1️.Confesional,2️.Testimonial,3️.Documental Pública o Privada,4️.Presuncional Legal y Humana,5️.Instrumental de Actuaciones,Escribe el número de la opción que deseas elegir, o escribe 'omitir' si no deseas proporcionarlo, o 'cancelar' para salir."
                        audio_response_path = text_to_speech(texto)
                        return jsonify({
                            "response": (
                                "✅ Se han registrado tus medidas de protección.\n\n"
                                f"Ahora necesito **{siguiente_dato}**.\n\n"
                                "¿Qué tipo de prueba deseas ofrecer? Elige una opción:\n"
                                "1️⃣ Confesional\n"
                                "2️⃣ Testimonial\n"
                                "3️⃣ Documental Pública o Privada\n"
                                "4️⃣ Presuncional Legal y Humana\n"
                                "5️⃣ Instrumental de Actuaciones\n\n"
                                "Escribe el número de la opción que deseas elegir, "
                                "o escribe 'omitir' si no deseas proporcionarlo, o 'cancelar' para salir."
                            ),
                            "audio_response": audio_response_path
                        })
                    else:
                        # Generar denuncia
                        try:
                            resultado = procesar_denuncia(datos_usuario)
                            if isinstance(resultado, dict) and "error" in resultado:
                                session["datos_faltantes"] = resultado["faltantes"]
                                return jsonify({
                                    "response": (f"⚠️ Faltan datos: {', '.join(resultado['faltantes'])}. "
                                                "Por favor, ingrésalos para continuar."),
                                    "audio_response": audio_response_path
                                })
                            session["pdf_path"] = resultado
                            session.pop("datos_faltantes", None)
                            session.pop("datos_usuario", None)
                            texto = "La denuncia ha sido generada correctamente. Puedes descargarla en el link que te genere. Este es un formato de denuncia con los datos proporcionados. Puedes revisarlo y editarlo si lo deseas. ¡Estoy aquí para ayudarte!"
                            audio_response_path = text_to_speech(texto)
                            return jsonify({
                                "response": (
                                    "✅ La denuncia ha sido generada correctamente. "
                                    "Puedes descargarla aquí: /download_sue\n\n"
                                    "Este es un formato de denuncia con los datos proporcionados. "
                                    "Puedes revisarlo y editarlo si lo deseas. "
                                    "¡Estoy aquí para ayudarte! 😊"
                                ),
                                "audio_response": audio_response_path
                            })
                        except Exception as e:
                            return jsonify({"response": f"❌ Error al generar la denuncia: {str(e)}"}), 500

                # Manejo de 'otra'
                if user_message == "otra":
                    texto = "Escribe la medida de protección adicional que deseas. Cuando termines, escribe 'terminar'."
                    audio_response_path = text_to_speech(texto)
                    return jsonify({
                        "response": (
                            "Escribe la medida de protección adicional que deseas. "
                            "Cuando termines, escribe 'terminar'."
                        ),
                        "audio_response": audio_response_path
                    })

                # Interpretar la selección
                selecciones = [s.strip() for s in user_message.split(",")]
                added_something = False

                for sel in selecciones:
                    if sel.isdigit():
                        idx = int(sel) - 1
                        if 0 <= idx < len(MEDIDAS_PROTECCION_OPCIONES):
                            datos_usuario["medidas_proteccion_lista"].append(MEDIDAS_PROTECCION_OPCIONES[idx])
                            added_something = True
                    else:
                        # Agregar medidas personalizadas
                        if sel:
                            datos_usuario["medidas_proteccion_lista"].append(sel)
                            added_something = True

                session["datos_usuario"] = datos_usuario
                texto = "Medidas de protección seleccionadas:" + "\n".join(f"- {m}" for m in datos_usuario["medidas_proteccion_lista"]) + "\n\nEscribe más números, 'otra' para añadir otra, o 'terminar' si has terminado con las medidas de protección."
                audio_response_path = text_to_speech(texto)
                return jsonify({
                    "response": (
                        "Medidas de protección seleccionadas:\n"
                        + "\n".join(f"- {m}" for m in datos_usuario["medidas_proteccion_lista"])
                        + "\n\nEscribe más números, 'otra' para añadir otra, "
                        "o 'terminar' si has terminado con las medidas de protección."
                    ),
                    "audio_response": audio_response_path
                })
            # --------------------------------
            #  3) PRUEBAS
            # --------------------------------
            if dato_actual == "tipo_prueba":
                if "ha_preguntado_tipo_prueba" not in session:
                    session["ha_preguntado_tipo_prueba"] = True
                    texto = "¿Qué tipo de prueba deseas ofrecer? Elige una opción: 1️.Confesional,2️.Testimonial, 3️.Documental Pública o Privada, 4️.Presuncional Legal y Humana, 5️.Instrumental de Actuaciones, Escribe el número de la opción que deseas elegir. puedes escribir para omitir o cancelar para terminar el proceso"
                    audio_response_path = text_to_speech(texto)
                    return jsonify({
                        "response": (
                            "¿Qué tipo de prueba deseas ofrecer? Elige una opción:\n"
                            "1️⃣ Confesional\n"
                            "2️⃣ Testimonial\n"
                            "3️⃣ Documental Pública o Privada\n"
                            "4️⃣ Presuncional Legal y Humana\n"
                            "5️⃣ Instrumental de Actuaciones\n"
                            "Escribe el número de la opción que deseas elegir."
                        ),
                        "audio_response": audio_response_path
                    })

                if user_message in ["1", "2", "3", "4", "5"]:
                    tipos_prueba = {
                        "1": "Confesional",
                        "2": "Testimonial",
                        "3": "Documental Pública o Privada",
                        "4": "Presuncional Legal y Humana",
                        "5": "Instrumental de Actuaciones"
                    }
                    
                    datos_usuario["tipo_prueba"] = tipos_prueba[user_message]
                    session["datos_usuario"] = datos_usuario

                    # **💡 IMPORTANTE: Eliminar `tipo_prueba` de `datos_faltantes`**
                    session["datos_faltantes"] = session["datos_faltantes"][1:]

                    if user_message == "1":  # Confesional
                        session["datos_faltantes"].extend([
                            "quien_desahoga", "numero_notarial", "notario_publico_numero", 
                            "donde_funciones_notario", "fecha_intrumento_notarial", 
                            "prueba_confesional", "numeros_prueba"
                        ])
                        return jsonify({
                            "response": "Has seleccionado prueba confesional. ¿Quién desahoga la prueba?",
                            "audio_response": audio_response_path
                        })

                    elif user_message == "2":  # Testimonial
                        session["datos_faltantes"].extend([
                            "quien_desahoga", "numero_notarial", "notario_publico_numero", 
                            "donde_funciones_notario", "fecha_intrumento_notarial", 
                            "prueba_testimonial", "numeros_prueba"
                        ])
                        return jsonify({
                            "response": "Has seleccionado prueba testimonial. ¿Quién desahoga la prueba?",
                            "audio_response": audio_response_path
                        })

                    elif user_message == "3":  # Documental Pública o Privada
                        session["datos_faltantes"].extend([
                            "documentos_oficiales", "folio", "fecha_folio", 
                            "autoridad_emite", "acto_documento", "documento_prueba", "numeros_prueba"
                        ])
                        return jsonify({
                            "response": "Has seleccionado prueba documental. ¿Cuál es el documento oficial que presentas?",
                            "audio_response": audio_response_path
                        })

                    elif user_message in ["4", "5"]:  # Presuncional Legal y Humana o Instrumental de Actuaciones
                        if user_message == "4":
                            datos_usuario["tipo_prueba"] = "presuncional"
                        else:
                            datos_usuario["tipo_prueba"] = "instrumental"

                        # **Eliminamos los datos dependientes que no aplican**
                        datos_omitidos = [
                            "quien_desahoga", "numero_notarial", "notario_publico_numero",
                            "donde_funciones_notario", "fecha_intrumento_notarial",
                            "prueba_confesional", "prueba_testimonial", "documento_prueba",
                            "numeros_prueba","folio","fecha_folio", "documentos_oficiales"
                        ]

                        session["datos_faltantes"] = [dato for dato in session.get("datos_faltantes", []) if dato not in datos_omitidos]

                        session["datos_usuario"] = datos_usuario

                        # **💡 IMPORTANTE: Avanzar al siguiente campo**
                        if session["datos_faltantes"]:
                            siguiente_dato = session["datos_faltantes"][0]
                            texto = f"Se ha registrado tu prueba {datos_usuario['tipo_prueba']}. Ahora necesito {siguiente_dato}."
                            audio_response_path = text_to_speech(texto)
                            return jsonify({
                                "response": markdown.markdown(f"✅ Se ha registrado tu prueba {datos_usuario['tipo_prueba']}. Ahora necesito **{siguiente_dato}**."),
                                "audio_response": audio_response_path
                            })
                        else:
                            resultado = procesar_denuncia(datos_usuario)
                            if isinstance(resultado, dict) and "error" in resultado:
                                session["datos_faltantes"] = resultado["faltantes"]
                                return jsonify({
                                    "response": f"⚠️ Faltan datos: {', '.join(resultado['faltantes'])}. Por favor, ingrésalos para continuar.",
                                })
                            session["pdf_path"] = resultado
                            session.pop("datos_faltantes", None)
                            session.pop("datos_usuario", None)
                            texto = "La denuncia ha sido generada correctamente. Puedes descargarla en el link que te genere. Este es un formato de denuncia con los datos proporcionados. Puedes revisarlo y editarlo si lo deseas. ¡Estoy aquí para ayudarte!"
                            audio_response_path = text_to_speech(texto)
                            return jsonify({
                                "response": "✅ La denuncia ha sido generada correctamente. Puedes descargarla aquí: /download_sue",
                                "audio_response": audio_response_path
                            })

                return jsonify({
                    "response": "Por favor, selecciona una opción válida (1-5) para el tipo de prueba."
                })

            # --------------------------------
            #  4) NARRACIONES
            # --------------------------------
            if dato_actual == "narraciones":
                if "narraciones" not in datos_usuario:
                    datos_usuario["narraciones"] = []

                if user_message.lower() in ["agregar", "otro"]:
                    return jsonify({"response": "Describe el siguiente hecho. Cuando termines, escribe 'terminar' o 'agregar' si quieres más."})

                if user_message.lower() == "terminar":
                    texto_final = "\n\n".join(datos_usuario["narraciones"])
                    datos_usuario["narraciones"] = texto_final
                    session["datos_usuario"] = datos_usuario
                    session["datos_faltantes"] = datos_faltantes[1:]
                    
                    if session["datos_faltantes"]:
                        siguiente_dato = session["datos_faltantes"][0]
                        desc = field_info.get(dato_actual, {}).get("descripcion", "Información no disponible.")
                        ejemp = field_info.get(dato_actual, {}).get("ejemplo", "Ejemplo no disponible.")
                        texto = (
                            f"Se han registrado tus narraciones. Ahora necesitamos {siguiente_dato}, {desc}. "
                            f"Un ejemplo de como llenarlo seria: {ejemp}. "
                            "¿Podrías proporcionarlo ahora?. Si no deseas darlo, escribe 'omitir', o 'cancelar'."
                        )
                        audio_response_path = text_to_speech(texto)
                        return jsonify({
                            "response": markdown.markdown(
                                "✅ Se han registrado tus narraciones.\n\n"
                                f"Ahora necesitamos **{siguiente_dato}**, {desc}.\n\n"
                                f"{ejemp}\n\n"
                                "¿Podrías proporcionarlo ahora? "
                                "Si no deseas darlo, escribe 'omitir', o 'cancelar'."
                            ),
                            "audio_response": audio_response_path
                        })
                    else:
                        # Generar denuncia
                        try:
                            resultado = procesar_denuncia(datos_usuario)
                            if isinstance(resultado, dict) and "error" in resultado:
                                session["datos_faltantes"] = resultado["faltantes"]
                                return jsonify({
                                    "response":markdown.markdown(f"⚠️ Faltan datos: {', '.join(resultado['faltantes'])}. "
                                                 "Por favor, ingrésalos para continuar.")
                                })
                            session["pdf_path"] = resultado
                            session.pop("datos_faltantes", None)
                            session.pop("datos_usuario", None)
                            texto = "La denuncia ha sido generada correctamente. Puedes descargarla en el link que te genere. Este es un formato de denuncia con los datos proporcionados. Puedes revisarlo y editarlo si lo deseas. ¡Estoy aquí para ayudarte!"
                            audio_response_path = text_to_speech(texto)
                            return jsonify({
                                "response": markdown.markdown(
                                    "✅ La denuncia ha sido generada correctamente. "
                                    "Puedes descargarla aquí: /download_sue\n\n"
                                    "Este es un formato de denuncia con los datos que me proporcionaste. "
                                    "Si deseas, puedes revisarlo y editarlo si lo consideras necesario. "
                                    "¡Estoy para ayudarte! 😊"
                                ),
                                "audio_response": audio_response_path
                            })
                        except Exception as e:
                            return jsonify({
                                "response": f"❌ Error al generar la denuncia: {str(e)}"
                            }), 500

                if not es_narracion_valida(user_message):
                    return jsonify({"response": "⚠️ Tu texto no cumple con la longitud mínima (10 caracteres). Por favor, da más detalles."})

                # Nuevo prompt modificado
                narraciones_prompt = f"""
                Eres un validador de narrativas de violencia política. Evalúa si el texto cumple:
                1. Fecha concreta (ej: 5 de febrero de 2023)
                2. Lugar identificable (ej: oficina de X en calle Y)
                3. Cita textual o descripción específica de los hechos
                4. Menciona al menos un derecho vulnerado

                Texto a validar: "{user_message}"

                INSTRUCCIONES DE RESPUESTA (sin agregar ni quitar nada):
                - Si el texto cumple TODOS los requisitos, responde EXACTAMENTE:
                se ha registrado narraciones

                - Si NO cumple TODOS los requisitos, responde SOLO con un texto 
                que empiece con:
                FALTAN REQUISITOS:

                Inmediatamente después, enlista en viñetas concretas 
                cuál o cuáles requisitos faltan.  
                Por ejemplo:
                - Falta fecha concreta
                - Falta lugar identificable
                - Falta cita textual
                - Falta mención de un derecho vulnerado

                Después de la lista, incluye la frase:
                "Ejemplo de narración que cumple los requisitos:"
                y proporciona un ejemplo breve que contenga fecha, 
                lugar, cita textual y mención de un derecho vulnerado.

                No formules preguntas. 
                No uses signos de interrogación. 
                No incluyas saludos ni conclusiones adicionales.
                No asumas que el usuario tiene dudas; sé directo.
                """


                completion_llm = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[{"role": "system", "content": narraciones_prompt},
                              {"role": "user", "content": "Validar el texto anterior"}
                            ],
                    temperature=0
                )
                
                bot_ans = completion_llm.choices[0].message.content if completion_llm.choices else ""

                if "se ha registrado narraciones":
                    datos_usuario["narraciones"].append(user_message.strip())
                    session["datos_usuario"] = datos_usuario
                    texto = "Narración agregada. ¿Deseas agregar otro hecho o terminar?"
                    audio_response_path = text_to_speech(texto)
                    return jsonify({
                        "response": markdown.markdown(
                            "✅ Narración agregada.\n\n"
                            "¿Deseas **agregar** otro hecho o **terminar**?"
                        ),
                        "audio_response": audio_response_path
                    })
                else:
                    datos_usuario["narraciones"].append(user_message.strip())  # la guardas igual
                    return jsonify({"response": f"Tu narración se guardó, pero faltan algunos criterios. GPT sugiere:\n{bot_ans}"})


            # -------------------------------------------------------------------
            # 2) Validación del dato ingresado con el LLM (código existente)
            # -------------------------------------------------------------------
            validation_func = VALIDATION_RULES.get(dato_actual)
            if validation_func:
                if not validation_func(user_message):
                    # ❌ Valor claramente inválido
                    return jsonify({
                        "response": markdown.markdown(
                            f"⚠️ El valor **{user_message}** no es válido para **{dato_actual}** "
                            f"según las reglas mínimas. Inténtalo de nuevo, "
                            "escribe 'omitir' para dejarlo vacío, o 'cancelar' para salir."
                        ),
                        "audio_response": audio_response_path
                    })
            desc = field_info.get(dato_actual, {}).get("descripcion", "Información no disponible.")
            ejemp = field_info.get(dato_actual, {}).get("ejemplo", "Ejemplo no disponible.")
            full_prompt = f"""
            {SYSTEM_PROMPT}
            ### Instrucciones para el LLM:
            1. El usuario está llenando un **formato de denuncia** y debe ingresar el siguiente dato: **{dato_actual}**.
            2. Aplica las reglas de validación de abajo (según el campo).  
            - **Si** el dato es válido, responde con la frase exacta: "**se ha registrado {dato_actual}**".
            - **Si** es inválido:
                - Explica por qué no es válido (formato, longitud, etc.).
                - Da un ejemplo correcto.
                - Pídele que lo ingrese de nuevo (no usar la frase "se ha registrado").
                - **No** avances al siguiente campo.
            3. Si el usuario escribe "omitir", deja este dato en blanco y pasa al siguiente.
            4. Si el usuario escribe "cancelar", se cancela el proceso.
            5. No avances ni confirmes el dato hasta que sea realmente válido.

            ### Reglas de validación (ejemplo):
            - **nombre_completo**  
            - Al menos 2 palabras (ej.: "María Pérez").  
            - No puede ser solo números ni un nombre incompleto.  
            - **telefono**  
            - Solo dígitos (0-9).  
            - Longitud mínima 7 (ej.: "5523456789").  
            - **correo**  
            - Debe contener '@' y un dominio (ej.: "ejemplo@dominio.com").  
            ##
            ### Contexto:
            - **Dato solicitado:** {dato_actual}
            - **Valor ingresado por el usuario:** "{user_message}"

            Explica por qué este dato es importante en el proceso de denuncia.  
            Si el usuario pide omitir o cancelar, respeta esa decisión.  

            """


            messages = session["messages"]
            messages.append({"role": "user", "content": user_message})

            completion = client.chat.completions.create(
                model="gpt-4-turbo",
                messages=[{"role": "system", "content": full_prompt}] + messages,
                max_tokens=500
            )
            bot_response = (completion.choices[0].message.content
                            if completion.choices else "No se pudo obtener una respuesta clara.")

            # Persistimos la conversación
            session["messages"] = messages

            # ¿el LLM confirma que el dato es válido?
            if any(frase in bot_response.lower() for frase in [
                "dato registrado", "se ha registrado", "ha sido guardado",
                "válido", "correcto", "registrado"]):   
                datos_usuario[dato_actual] = user_message.strip()
                session["datos_usuario"] = datos_usuario
                session["datos_faltantes"] = datos_faltantes[1:]

                if session["datos_faltantes"]:
                    siguiente_dato = session["datos_faltantes"][0]
                    desc = field_info.get(siguiente_dato, {}).get("descripcion", "Información no disponible.")
                    ejemp = field_info.get(siguiente_dato, {}).get("ejemplo", "Ejemplo no disponible.")
                    texto = f"se ha registrado {dato_actual}. El siguiente dato es {siguiente_dato}, que sirve {desc}. {ejemp},¿Podrías proporcionarlo?"
                    audio_response_path = text_to_speech(texto)
                    return jsonify({
                        "response": markdown.markdown(
                            f"✅ Se ha registrado **{dato_actual}**.\n\n"
                            f"El siguiente dato es **{siguiente_dato}**, "
                            f"que sirve {desc}.\n\n"
                            f"{ejemp}\n\n"
                            "¿Podrías proporcionarlo?"
                        ),
                        "audio_response": audio_response_path
                    })
                else:
                    # Generar denuncia
                    try:
                        resultado = procesar_denuncia(datos_usuario)
                        
                        if isinstance(resultado, dict) and "error" in resultado:
                            session["datos_faltantes"] = resultado["faltantes"]
                            texto = f"Faltan datos: {', '.join(resultado['faltantes'])}. Por favor, ingrésalos para continuar."
                            audio_response_path = text_to_speech(texto)
                            return jsonify({
                                "response": (f"⚠️ Faltan datos: {', '.join(resultado['faltantes'])}. "
                                             "Por favor, ingrésalos para continuar."),
                                "audio_response": audio_response_path
                            })

                        session["pdf_path"] = resultado
                        session.pop("datos_faltantes", None)
                        session.pop("datos_usuario", None)
                        texto = "La denuncia ha sido generada correctamente. Puedes descargarla en el link que te genere. Este es un formato de denuncia con los datos proporcionados. Puedes revisarlo y editarlo si lo deseas. ¡Estoy aquí para ayudarte!"
                        audio_response_path = text_to_speech(texto)
                        return jsonify({
                            "response": (
                                "✅ La denuncia ha sido generada correctamente. "
                                "Puedes descargarla aquí: /download_sue\n\n"
                                "Este es un formato de denuncia con los datos proporcionados. "
                                "Puedes revisarlo y editarlo si lo deseas. "
                                "¡Estoy aquí para ayudarte! 😊"
                            ),
                            "audio_response": audio_response_path
                        })
                    except Exception as e:
                        return jsonify({
                            "response": f"❌ Error al generar la denuncia: {str(e)}"
                        }), 500

            # Si el LLM no confirma, devolvemos la respuesta para que el usuario corrija
            return jsonify({"response": bot_response})

        # -----------------------------------------------------------------------
        # 2) Si NO se está llenando datos, revisamos si el usuario quiere iniciar denuncia
        # -----------------------------------------------------------------------
        frases_activadoras = [
            "quiero hacer una denuncia",
            "necesito denunciar",
            "quiero denunciar"
        ]
        user_message_clean = re.sub(r"[^\w\s]", "", user_message.lower()).strip()
        if user_message_clean in frases_activadoras:
            session["awaiting_decision"] = True
            texto = "¿Qué deseas hacer?. 1️.Iniciar el proceso de denuncia. 2️.Recibir orientación antes de denunciar. Escribe '1' para iniciar la denuncia o '2' para orientación."
            audio_response_path = text_to_speech(texto)
            return jsonify({
                "response": markdown.markdown(
                    "🔍 ¿Qué deseas hacer?\n\n"
                    "1️⃣ **📄 Iniciar el proceso de denuncia.**\n"
                    "2️⃣ **🧠 Recibir orientación antes de denunciar.**\n\n"
                    "Escribe '1' para iniciar la denuncia o '2' para orientación."
                ),
                "audio_response": audio_response_path
            })

        # 2.1) Manejo de la decisión
        if session.get("awaiting_decision"):
            if user_message in respuestas_proceder or user_message == "1":
                session.pop("awaiting_decision", None)
                # Aquí definimos la lista COMPLETA de campos faltantes
                session["datos_faltantes"] = LISTA_CAMPOS_DENUNCIA.copy()
                session["datos_usuario"] = {}

                primer_dato = session["datos_faltantes"][0]
                texto = f"Perfecto, iniciaremos la denuncia. A continuación te mostraré la lista de datos que necesitaremos y por qué son importantes: 1.Nombre completo: Para identificar formalmente a la persona que presenta la denuncia. 2.Teléfono Un medio de contacto para resolver dudas o enviar notificaciones. 3.Domicilio: Tu dirección oficial, necesaria en algunos trámites legales. 4.Correo Para envío de notificaciones y seguimiento digital. 5.Personas autorizadas: Si deseas que alguien más reciba notificaciones o te ayude en el proceso. 6.Fecha de los hechos: El día en que ocurrieron los hechos que denuncias. 7.Lugar de los hechos: Dónde sucedieron esos hechos. 8.Ciudad: Ubicación general para contextualizar lo ocurrido. 9.Persona denunciada: Nombre completo de la persona a quien diriges la denuncia. 10.Relación con la persona denunciada: Si es familiar, colega, etc. 11.Narración de los hechos: Descripción detallada de lo que ocurrió. 12.Afectación: Cómo te impactaron estos hechos. 13.Medidas cautelares: Acciones urgentes que solicitas para proteger tus derechos. 14.Protección: Medidas adicionales de protección que consideras necesarias.15.Pruebas: Testimonios, documentos u otras evidencias que respalden la denuncia. Te iré solicitando estos datos uno por uno. Puedes omitir un dato si no lo deseas proporcionar, o escribir cancelar para detener el proceso en cualquier momento. Para comenzar, por favor, indícame {primer_dato}."
                audio_response_path = text_to_speech(texto)
                respuesta = (
                        "Perfecto, iniciaremos la denuncia. A continuación te mostraré la lista "
                        "de datos que necesitaremos y por qué son importantes:\n"
                        
                        "1. **Nombre completo**: Para identificar formalmente a la persona que presenta la denuncia.\n"
                        "2. **Teléfono**: Un medio de contacto para resolver dudas o enviar notificaciones.\n"
                        "3. **Domicilio**: Tu dirección oficial, necesaria en algunos trámites legales.\n"
                        "4. **Correo**: Para envío de notificaciones y seguimiento digital.\n"
                        "5. **Personas autorizadas**: Si deseas que alguien más reciba notificaciones o te ayude en el proceso.\n"
                        "6. **Fecha de los hechos**: El día en que ocurrieron los hechos que denuncias.\n"
                        "7. **Lugar de los hechos**: Dónde sucedieron esos hechos.\n"
                        "8. **Ciudad**: Ubicación general para contextualizar lo ocurrido.\n"
                        "9. **Persona denunciada**: Nombre completo de la persona a quien diriges la denuncia.\n"
                        "10. **Relación con la persona denunciada**: Si es familiar, colega, etc.\n"
                        "11. **Narración de los hechos**: Descripción detallada de lo que ocurrió.\n"
                        "12. **Afectación**: Cómo te impactaron estos hechos.\n"
                        "13. **Medidas cautelares**: Acciones urgentes que solicitas para proteger tus derechos.\n"
                        "14. **Protección**: Medidas adicionales de protección que consideras necesarias.\n"
                        "15. **Pruebas**: Testimonios, documentos u otras evidencias que respalden la denuncia.\n\n"

                        "Te iré solicitando estos datos uno por uno. Puedes **omitir** un dato si no "
                        "lo deseas proporcionar, o escribir **cancelar** para detener el proceso en cualquier momento.\n\n"
                        
                        f"Para comenzar, por favor, indícame **{primer_dato}**."
                    )
                respuesta_html = markdown.markdown(respuesta)
                return jsonify({
                    "response": respuesta_html,
                    "audio_response": audio_response_path
                })

            elif user_message in respuestas_no or user_message == "2":
                # El usuario quiere orientación antes de denunciar
                session["awaiting_orientation_response"] = True
                session.pop("awaiting_decision", None)

                messages = session["messages"]
                messages.append({"role": "user", "content": "¿Cómo puedo presentar una denuncia?"})

                completion = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                    max_tokens=500
                )

                bot_response = (completion.choices[0].message.content
                                if completion.choices else "No se pudo obtener una respuesta clara.")

                # Persistimos mensajes
                session["messages"] = messages
                texto = bot_response + "\n\n🔹 ¿Te puedo ayudar en algo más?"
                audio_response_path = text_to_speech(bot_response)
                
                return jsonify({
                    "response": markdown.markdown(bot_response + "\n\n🔹 **¿Te puedo ayudar en algo más?**"),
                    "audio_response": audio_response_path
                })

        # -----------------------------------------------------------------------
        # 3) Chat general si no se ha iniciado o no se está en proceso de denuncia
        # -----------------------------------------------------------------------
        messages = session["messages"]
        messages.append({"role": "user", "content": user_message})

        completion = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            max_tokens=500
        )
        bot_response = (completion.choices[0].message.content 
                        if completion.choices else "")

        # Actualizar 'messages'
        session["messages"] = messages

        # Manejo de respuestas vagas
        vague_responses = ["no estoy seguro", "no tengo información", "no puedo responder"]
        if any(vague in bot_response.lower() for vague in vague_responses):
            retrieved_context = search_in_pdfs(user_message)
            if retrieved_context:
                full_prompt = f"""
                {SYSTEM_PROMPT}
                El usuario ha preguntado: "{user_message}"
                No se encontró una respuesta clara, pero aquí hay información relevante:
                {retrieved_context}
                Responde de manera clara y útil utilizando esta información.
                """
                completion = client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=[{"role": "system", "content": full_prompt}] + messages,
                    max_tokens=500
                )
                bot_response = (completion.choices[0].message.content 
                                if completion.choices else "No se pudo obtener una respuesta clara.")

        bot_response_html = markdown.markdown(bot_response)
        audio_response_path = text_to_speech(bot_response)
        return jsonify({
            "response": bot_response_html,
            "audio_response": audio_response_path
        })
    except Exception as e:
        return jsonify({"response": f"Error: {str(e)}"}), 500

@app.route("/audio", methods=["POST"])
def audio():
    if "audio" not in request.files:
        return jsonify({"error": "No se recibió ningún archivo de audio."}), 400

    audio_file = request.files["audio"]
    if audio_file.filename == "":
        return jsonify({"error": "El archivo no tiene nombre."}), 400

    # Guardar el archivo en el servidor
    filename = secure_filename(audio_file.filename)
    file_path = os.path.join(AUDIO_FOLDER, filename)
    audio_file.save(file_path)

    try:
        # Transcribir el audio usando OpenAI Whisper
        with open(file_path, "rb") as f:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=f)

        transcription_text = transcript.text if hasattr(transcript, "text") else "[No se obtuvo transcripción]"

        # Enviar el texto transcrito como mensaje al chat
        chat_response = chat_request(transcription_text)

        # Convertir la respuesta del bot en HTML con markdown
        response_html = markdown.markdown(chat_response["response"])

        # Convertir la respuesta del bot en audio
        audio_response_path = text_to_speech(chat_response["response"])

        return jsonify({
            "response": response_html,  # Ahora la respuesta es en HTML
            "transcription": transcription_text,
            "audio_response": audio_response_path
        })

    except Exception as e:
        return jsonify({"error": f"Error al procesar el audio: {str(e)}"}), 500
    
@app.route('/static/audio/<filename>')
def serve_audio(filename):
    return send_file(os.path.join("static/audio", filename))

def chat_request(user_message):
    """Función para enviar una consulta al chatbot desde texto."""
    messages = session.get("messages", [])
    messages.append({"role": "user", "content": user_message})

    try:
        completion = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            max_tokens=500
        )
        bot_response = completion.choices[0].message.content if completion.choices else ""

        messages.append({"role": "assistant", "content": bot_response})
        session["messages"] = messages

        return {"response": bot_response}

    except Exception as e:
        return {"response": f"Error: {str(e)}"}
    
@app.route("/get_messages")
def get_messages():
    messages = session.get("messages", [])
    return jsonify({"messages": messages})

@app.route("/confirm_clear", methods=["POST"])
def confirm_clear():
    """
    Ahora, en lugar de solo remover 'messages', eliminamos TODO con session.clear().
    Así reseteas la sesión por completo (datos faltantes, pdf_path, etc.).
    """
    session.clear()
    return jsonify({"response": "Memoria y sesión limpiadas. 🧹"})

@app.route("/download_form", methods=["GET"])
def download_form():
    pdf_path = "formato/Formulario_Formato_de_Denuncia_VPCMRG_listo.pdf"
    return send_file(pdf_path, as_attachment=True)

@app.route("/download_sue", methods=["GET"])
def download_sue():
    pdf_path = session.get("pdf_path")

    if not pdf_path:
        print("❌ No hay un PDF en la sesión.")  # Debugging
        return jsonify({"error": "No se ha generado ningún archivo en la sesión."}), 404

    if not isinstance(pdf_path, str):
        print(f"❌ Error: pdf_path en sesión no es un string: {pdf_path}")  # Debugging
        return jsonify({"error": "Ruta de PDF inválida en la sesión."}), 500

    pdf_path = os.path.abspath(pdf_path)  # Convertir a ruta absoluta

    if not os.path.exists(pdf_path):
        print(f"❌ Error: El archivo no existe en {pdf_path}")  # Debugging
        return jsonify({"error": f"El archivo no existe en: {pdf_path}"}), 404

    return send_file(pdf_path, as_attachment=True)

@app.route("/get_pdf_path", methods=["GET"])
def get_pdf_path():
    pdf_path = session.get("pdf_path")

    if not pdf_path:
        return jsonify({"error": "No se ha generado ningún archivo en la sesión."}), 404

    return jsonify({"pdf_path": pdf_path})  # ✅ Ahora devuelve un diccionario válido

@app.route("/generar_denuncia", methods=["POST"])
def generar_denuncia():
    try:
        # Obtener datos del JSON recibido
        data = request.get_json()

        # Validar si recibimos datos
        if not data:
            return jsonify({"error": "No se enviaron datos para la denuncia."}), 400

        # Procesar denuncia y generar PDF
        resultado = procesar_denuncia(data)

        # Si hubo un error por datos faltantes
        if isinstance(resultado, dict) and "error" in resultado:
            return jsonify(resultado), 400

    
        return jsonify({"message": "Denuncia generada con éxito."})

    except Exception as e:
        return jsonify({"error": f"Error al generar la denuncia: {str(e)}"}), 500

if __name__ == "__main__":
    with db_lock:  # Garantiza que solo un hilo cargue el índice FAISS
        if db is None and not app.debug:  
            db = load_or_create_index()

    app.run(host="0.0.0.0", port=5000, debug=False)
