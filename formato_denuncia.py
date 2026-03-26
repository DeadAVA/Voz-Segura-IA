from fpdf import FPDF
from datetime import datetime
import re

# Diccionario para traducir los meses al español
meses_es = {
    "January": "enero", "February": "febrero", "March": "marzo", "April": "abril",
    "May": "mayo", "June": "junio", "July": "julio", "August": "agosto",
    "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre"
}

# Diccionario de ciudades y sus respectivos estados abreviados
ciudad_estado = {
    "ensenada": "BC", "mexicali": "BC", "tijuana": "BC", "la paz": "BCS",
    "los cabos": "BCS", "campeche": "CAMP", "tuxtla gutiérrez": "CHIS",
    "chihuahua": "CHIH", "juárez": "CHIH", "saltillo": "COAH", "torreón": "COAH",
    "colima": "COL", "manzanillo": "COL", "durango": "DGO", "león": "GTO",
    "celaya": "GTO", "acapulco": "GRO", "pachuca": "HGO", "guadalajara": "JAL",
    "morelia": "MICH", "cuernavaca": "MOR", "monterrey": "NL", "oaxaca": "OAX",
    "puebla": "PUE", "querétaro": "QRO", "cancún": "QROO", "san luis potosí": "SLP",
    "mazatlán": "SIN", "culiacán": "SIN", "hermosillo": "SON", "villahermosa": "TAB",
    "tampico": "TAMPS", "xalapa": "VER", "veracruz": "VER", "merida": "YUC",
    "zacatecas": "ZAC", "ciudad de méxico": "CDMX"
}

def obtener_fecha_mx():
    fecha_actual = datetime.now()
    mes_en_ingles = fecha_actual.strftime("%B")  # Obtiene el mes en inglés
    mes_en_espanol = meses_es[mes_en_ingles]  # Traduce al español
    return fecha_actual.strftime(f"%d de {mes_en_espanol} de %Y")

def solicitar_datos_faltantes(datos, datos_faltantes):
    """Llena los datos faltantes con un espacio en blanco representado por líneas subrayadas."""
    for dato in datos_faltantes:
        datos[dato] = "_________________________"  # Se deja un espacio en blanco en el PDF
    return datos

def generar_texto_prueba(datos):
    textos_pruebas = {
        "confesional": "LA CONFESIONAL. Prueba que se ofrece en términos del artículo 461, párrafo 4 de la LGIPE y que corre a cargo de: {quien_desahoga}, misma que consta en la fe de hechos notarial número: {numero_notarial}, levantada ante la o el Notario Público número: {notario_publico_numero} con ejercicio en: {donde_funciones_notario}, el día: {fecha_intrumento_notarial}.\n\nCon esta prueba pretendo acreditar que la persona denunciada ha ejercido violencia en contra de la suscrita, consistente en: {prueba_confesional}.\n\nEsta prueba la relaciono con los hechos marcados con los números de la presente denuncia. {numeros_prueba}",
        "testimonial": "LA TESTIMONIAL. Prueba que se ofrece en términos del artículo 461 párrafo 4 de la LGIPE y que corre a cargo de: {quien_desahoga}, misma que consta en el instrumento notarial número: {numero_notarial}, levantado ante la o el Notario Público número: {notario_publico_numero} con ejercicio en: {donde_funciones_notario}, el día: {fecha_intrumento_notarial}.\n\nCon esta prueba pretendo acreditar que la persona denunciada ha ejercido violencia en contra de la suscrita, consistente en: {prueba_testimonial}.\n\nEsta prueba la relaciono con los hechos marcados con los números de la presente denuncia. {numeros_prueba}",
        "documental": "DOCUMENTAL PÚBLICA (PRIVADA): Consistente en el: {documentos_oficiales} identificado bajo el folio: {folio}, de fecha: {fecha_folio} por medio del cual: {autoridad_emite} señala que: {acto_documento}.\n\nCon esta prueba pretendo acreditar: {documento_prueba}.\n\nEsta prueba la relaciono con los hechos marcados con los números de la presente denuncia. {numeros_prueba}",
        "presuncional": "PRESUNCIONAL LEGAL Y HUMANA. En todo lo que favorezca a la suscrita consistente en los razonamientos lógico-jurídicos que realice esa autoridad.",
        "instrumental": "INSTRUMENTAL DE ACTUACIONES. Consistente en todas y cada una de las constancias que integran el expediente y que favorezcan a la suscrita."
    }
    
    tipo_prueba = datos.get("tipo_prueba", "")
    return textos_pruebas.get(tipo_prueba, "")

TEXTO_BASE = """

{nombre_completo}, por propio derecho, con número telefónico a efecto de ser localizada (o) con prontitud el: {telefono},
señalando como domicilio para oír y recibir todo tipo de notificaciones y documentos el ubicado en:
{domicilio};
como datos de correo electrónico para notificaciones electrónicas el siguiente: {correo}
y autorizando para tales efectos a: {persona_autorizada1} y {persona_autorizada2},
indistintamente, ante esta autoridad, comparezco y expongo:

Por medio del presente escrito, y en atención a lo dispuesto los artículos 1°, 4, 34 y 35 de
la Constitución Política de los Estados Unidos Mexicanos; artículos 1° y 5 de la Ley General para
la Igualdad entre Mujeres y Hombres; artículos 6, 11, 14, 15, 16, 18, 20 Bis, 20 Ter, 21, 27, 48 Bis,
52, fracción II, y 60 de la Ley General de Acceso a las Mujeres a una Vida Libre de Violencia, y
3, párrafo 1, inciso k), 159, 163, 247, párrafo 2, 442 Bis, 463 Bis, 463 Ter, 470, 474 Bis de la Ley
General de Instituciones y Procedimientos Electorales, vengo a denunciar a: {persona_denunciada},
con quien tengo una relación de: {relacion_denunciada},
por la comisión de hechos constitutivos de violencia política por razón de género.

Para hacerlo, fundo mi denuncia en las siguientes consideraciones de hecho y derecho.


HECHOS

El día: {fecha_hechos}, estando presentes en: {lugar_hechos},
el denunciado llevó a cabo las siguientes acciones en contra de mi persona por el hecho de ser
mujer, ya que...

{narraciones}

Los hechos narrados han causado una afectación en la suscrita, toda vez que dicha conducta vulneró mis siguientes derechos: {afectacion}.


MEDIDAS CAUTELARES

De acuerdo a las consideraciones que han sido narradas en la presente denuncia, solicito se de-
creten de inmediato las siguientes medidas cautelares:

{medidas_cautelares}

\tMEDIDAS DE PROTECCIÓN

Con fundamento en lo dispuesto en los artículos 463 Bis y 474 Bis de la Ley General de Institucio-
nes y Procedimientos Electorales; 1 y 2 de la Convención Americana sobre Derechos Humanos;
7, inciso f), de la Convención Interamericana para Prevenir, Sancionar y Erradicar la Violencia
contra la Mujer (Convención Belém Do Pará); 2, apartado d), y 3 de la Convención sobre la Elimi-
nación de Todas las Formas de Discriminación contra la Mujer; 52, fracción II, de la Ley General
de Acceso a las Mujeres a una Vida Libre de Violencia, y de acuerdo a las consideraciones que
han sido narradas en la presente denuncia, solicito se decrete de inmediato las siguientes medi-
das de protección:

Señalar las medidas que requiera se decreten a efecto de prevenir mayores daños, entre otros:

{medidas_proteccion}

PRUEBAS

Las pruebas deben ofrecerse señalando el tipo de prueba, en qué consiste, qué se pretende acreditar y relacionarla con los hechos controvertidos.

{tipo_prueba}


DERECHO
Marco normativo internacional
Los artículos 2, 3 y 26 del Pacto Internacional de Derechos Civiles y Políticos, dentro del Sistema
universal de Derechos Humanos; los artículos II y III de la Convención de los Derechos Políticos
de la Mujer; artículos 1, 2, 23 y 24 de la Convención Americana sobre Derechos Humanos; preám-
bulo, artículos 1, 2, 3 y 7 de la Convención sobre la Eliminación de Todas las Formas de Discri-
minación contra la Mujer (CEDAW), y artículo 7 de la Convención Interamericana para Prevenir,
Sancionar y Erradicar la Violencia contra la Mujer (Convención Belém Do Pará).
Marco normativo nacional
Los artículos 1°, 4, 34 y 35 de la Constitución Política de los Estados Unidos Mexicanos; artículos
1° y 5 de la Ley General para la Igualdad entre Mujeres y Hombres; artículos 6, 11, 14, 15, 16, 18,
20 Bis, 20 Ter, 21, 27, 48 Bis, 52, fracción II, y 60 de la Ley General de Acceso a las Mujeres a una
Vida Libre de Violencia, y 3, párrafo 1, inciso k), 159, 163, 247, párrafo 2, 442 Bis, 463 Bis, 463
Ter, 470, 474 Bis de la Ley General de Instituciones y Procedimientos Electorales.

El Protocolo de la Suprema Corte de Justicia de la Nación y el Protocolo para Atender la Violencia
Política Contra las Mujeres en razón de Género.
Por lo expuesto y fundado, a esta Unidad Técnica de lo Contencioso Electoral; atentamente se
sirva:

ÚNICO. Tenerme por presentada en los términos de este escrito, con las copias simples que se
acompañan, denunciando de los {persona_denunciada}
todas y cada una de las prestaciones que se hacen valer en el capítulo respectivo.

PROTESTO LO NECESARIO

"""

class PDF(FPDF):
    def header(self):
        if self.page_no() == 1:
            self.set_font("Times", "B", 12)
            self.cell(0, 10, "FORMATO DE DENUNCIA EN MATERIA DE VIOLENCIA POLÍTICA", ln=True, align="C")
            self.ln(10)

    def chapter_body(self, body):
        body = normalizar_texto(body)
        self.set_font("Times", "", 12)
        body = body.replace("\n", " ")
        self.multi_cell(0, 7, body, align="J")
        self.ln()
        
    def texto_negrita(self, texto):
        """Función para hacer el texto en negrita"""
        self.set_font("Times", "B", 12)
        texto = texto.replace("\n", " ")
        self.multi_cell(0, 7, texto, align="J")
        self.ln()
        
    def agregar_titulo_centrado(self, texto):
        """Agrega un título centrado en negritas."""
        self.set_font("Times", "B", 12)
        self.cell(0, 10, texto, ln=True, align="C")
        self.ln(5)

    def agregar_fecha_centrada(self, ciudad):
        """Agrega la fecha y la ciudad con el estado en el formato correcto."""
        fecha = obtener_fecha_mx()
        ciudad_formateada = ciudad.title()
        estado = ciudad_estado.get(ciudad.lower(), "Estado desconocido")
        
        # Si el estado es desconocido, solo pone la ciudad
        if estado != "Estado desconocido":
            ubicacion = f"{ciudad_formateada}, {estado}"
        else:
            ubicacion = ciudad_formateada
            
        self.set_font("Times", "", 12)
        self.cell(0, 10, f"{ubicacion} a {fecha}.", ln=True, align="C")
        self.ln(5)

    def agregar_firma_centrada(self):
        """Agrega un espacio de firma centrado."""
        self.ln(5)
        self.cell(0, 5, "_____________________________________________________", ln=True, align="C")
        self.cell(0, 5, "Nombre y firma de quien presenta la queja", ln=True, align="C")
        self.ln(10)
        
def normalizar_texto(body):
    # Reemplazar comillas “ ” por comillas normales "
    body = body.replace("“", "\"").replace("”", "\"")
    # Reemplazar comillas simples inclinadas o signos raros si aplica
    # ...
    return body

def extraer_datos(texto):
    """Extrae datos desde el texto del usuario y detecta cuáles faltan."""
    patrones = {
        "nombre_completo": r"Mi nombre es ([^.,]+)",
        "telefono": r"mi teléfono es ([^.,]+)",
        "domicilio": r"vivo en ([^.,]+)",
        "correo": r"mi correo es ([^.,]+)",
        "persona_autorizada1": r"autorizo a ([^.,]+)",
        "persona_autorizada2": r"y también a ([^.,]+)",
        "fecha_hechos": r"el (\d{1,2} de [a-zA-Z]+ de \d{4})",
        "lugar_hechos": r"en ([^.,]+) ocurrieron los hechos",
        "ciudad": r"en la ciudad de ([^.,]+)",
        "persona_denunciada": r"(?:denuncio a|quiero denunciar a|acuso a|reporto a)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
        "relacion_denunciada": r"quien es mi ([^.,]+)",
        "narraciones": r"porque (.+?)(?:\.|$)",
        "afectacion": r"esto me afectó porque ([^.,]+)",
        "medidas_cautelares": r"Solicito como medida | también solicito | Adicionalmente pido  ([^.,]+)",
        "medidas_proteccion": r"Necesito protección | Además de eso | Finalmente requiero ([^.,]+)",
        "tipo_prueba": r"opcion ([^.,]+)",
        "prueba_confesional": r"como prueba confesional presento ([^.,]+)",
        "prueba_testimonial": r"como prueba testimonial presento ([^.,]+)",
        "documento_prueba": r"documento que acredita ([^.,]+)",
        "quien_desahoga": r"quien desahoga la prueba es ([^.,]+)",
        "numero_notarial": r"consta en la fe de hechos notarial número ([^.,]+)",
        "notario_publico_numero": r"ante la o el Notario Público número ([^.,]+)",
        "donde_funciones_notario": r"con ejercicio en ([^.,]+)",
        "fecha_intrumento_notarial": r"el día ([^.,]+)",
        "numeros_prueba": r"hechos marcados con los números ([^.,]+)",
        "documentos_oficiales": r"documento oficial que presento ([^.,]+)",
        "folio": r"bajo el folio ([^.,]+)",
        "fecha_folio": r"de fecha ([^.,]+)",
        "autoridad_emite": r"emitido por ([^.,]+)",
        "acto_documento": r"el documento señala que ([^.,]+)"
    }
    
    datos = {key: None for key in patrones}
    datos_faltantes = []
    
    for key, pattern in patrones.items():
        match = re.search(pattern, texto, re.IGNORECASE)
        if match:
            datos[key] = match.group(1).strip()
        else:
            datos_faltantes.append(key)
    
    datos["fecha_presentacion"] = datetime.now().strftime("%d de %B de %Y")
    
    return datos, datos_faltantes

def generar_pdf(datos, output_path="formato_denuncia.pdf"):
    """Genera el PDF de la denuncia con los datos obtenidos, centrando los títulos y firma."""
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.texto_negrita("UNIDAD TÉCNICA DE LO CONTENCIOSO ELECTORAL DE LA SECRETARÍA EJECUTIVA DEL INSTITUTO NACIONAL ELECTORAL")
    
    # Contenido
    datos["tipo_prueba"] = generar_texto_prueba(datos)
    texto_completo = TEXTO_BASE.format(**datos)
    secciones = texto_completo.split("\n\n")
    for seccion in secciones:
        if seccion.strip():
            if "HECHOS" in seccion or "MEDIDAS CAUTELARES" in seccion or "MEDIDAS DE PROTECCIÓN" in seccion or "PRUEBAS" in seccion or "PROTESTO LO NECESARIO"in seccion or "HECHOS" in seccion:
                pdf.agregar_titulo_centrado(seccion.strip())
            else:
                pdf.chapter_body(seccion)
                

    # Fecha centrada
    pdf.agregar_fecha_centrada(datos["ciudad"])

    # Espacio para firma centrado
    pdf.agregar_firma_centrada()

    # Guardar PDF
    pdf.output(output_path)
    return output_path

def procesar_denuncia(entrada):
    """Procesa la denuncia y genera un PDF."""
    
    if isinstance(entrada, str):  
        datos, datos_faltantes = extraer_datos(entrada)
    elif isinstance(entrada, dict):  
        datos = entrada  
        datos_faltantes = [k for k, v in datos.items() if v is None]  # Detectar campos vacíos

    # Asegurar que `fecha_presentacion` esté presente antes de continuar
    if "fecha_presentacion" not in datos or not datos["fecha_presentacion"]:
        datos["fecha_presentacion"] = obtener_fecha_mx()

    if datos_faltantes:
        datos = solicitar_datos_faltantes(datos, datos_faltantes)  # Se llenan con espacios en blanco
        return {"error": "Faltan datos", "faltantes": datos_faltantes}

    # Generar el PDF
    pdf_path = generar_pdf(datos)
    return pdf_path


