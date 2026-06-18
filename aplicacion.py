"""
Raíces de Paz IA — Popayán Inteligente
App de demostración (Streamlit) para el Hackathon Cauca (Talento Tech / faceIT / UTP).

Reto: fortalecer el turismo en Popayán mediante una solución digital que
(1) mejore la visibilidad y promoción de atractivos turísticos,
(2) facilite la identificación y articulación de actores del ecosistema, y
(3) promueva una mejor cultura de servicio y atención al visitante.

Etapas: Chatbot · Robot guía por voz (ROBI) · Mapa explorador con detección de
imagen · Panel de reportes · AR (próximamente).

Las API keys se leen de Secrets de Streamlit (Settings → Secrets):
ANTHROPIC_API_KEY (Claude) y GOOGLE_MAPS_API_KEY (búsqueda de lugares y rutas).
"""

import base64
import json
import os
import sqlite3
import datetime
import urllib.parse
import urllib.request
import streamlit as st
import streamlit.components.v1 as components
import anthropic
from streamlit_mic_recorder import speech_to_text

# ----------------------------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Raíces de Paz IA · Popayán", page_icon="🌿", layout="centered")

MODELO_TEXTO = "claude-haiku-4-5-20251001"   # chatbot y robot (texto) — string versionado
MODELO_VISION = "claude-sonnet-4-6"          # mapa (análisis de imagen) — modelo vigente

CIUDAD = "Popayán, Cauca, Colombia"

# ----------------------------------------------------------------------------
# CATÁLOGO DE ATRACTIVOS REALES DE POPAYÁN Y EL CAUCA
# (Atractivo, Zona, Descripción corta) — fuente de visibilidad/promoción.
# ----------------------------------------------------------------------------
SITIOS = [
    ("Centro Histórico de Popayán", "Centro, Popayán", "La 'Ciudad Blanca': arquitectura colonial de fachadas blancas"),
    ("Semana Santa de Popayán", "Centro, Popayán", "Procesiones declaradas Patrimonio Cultural Inmaterial por la UNESCO"),
    ("Torre del Reloj", "Centro, Popayán", "Ícono colonial del siglo XVIII, símbolo de la ciudad"),
    ("Puente del Humilladero", "Centro, Popayán", "Puente de ladrillo de 1873, postal de Popayán"),
    ("Iglesia de San Francisco", "Centro, Popayán", "Joya del barroco con el altar más valioso de la ciudad"),
    ("Morro de Tulcán", "Popayán", "Pirámide precolombina y mirador con la estatua de Belalcázar"),
    ("Cerro de las Tres Cruces", "Popayán", "Mirador panorámico y senderismo urbano"),
    ("Museo Nacional Guillermo Valencia", "Centro, Popayán", "Casa del poeta payanés, historia y arte"),
    ("Gastronomía payanesa", "Popayán", "Ciudad Creativa de la Gastronomía UNESCO: empanadas de pipián, tamal, carantanta"),
    ("Pueblito Patojo", "Popayán", "Réplica a escala de los rincones típicos de la ciudad"),
    ("Silvia y mercado guambiano", "Silvia, Cauca", "Cultura misak, mercado indígena de los martes"),
    ("Parque Nacional Puracé y Termales", "Puracé, Cauca", "Volcán, cóndores andinos y aguas termales"),
    ("Tierradentro", "Inzá, Cauca", "Hipogeos y estatuaria precolombina, Patrimonio UNESCO"),
    ("Coconuco — Termales", "Coconuco, Cauca", "Aguas termales y paisaje de montaña cerca de Popayán"),
]
CATALOGO_TXT = "\n".join(f"- {n} ({z}): {d}" for n, z, d in SITIOS)

# ----------------------------------------------------------------------------
# ACTORES DEL ECOSISTEMA TURÍSTICO (articulación — objetivo 2 del reto)
# Categorías que un visitante o gestor querría identificar y conectar.
# ----------------------------------------------------------------------------
ACTORES = [
    ("Operadores y guías turísticos", "Empresas y guías locales certificados que arman experiencias."),
    ("Restaurantes y cocina tradicional", "Sostienen el sello de Ciudad Creativa de la Gastronomía."),
    ("Hoteles y hospedajes", "Desde hoteles boutique en casonas coloniales hasta hostales."),
    ("Artesanos y cultura misak", "Tejido, sombrero, productos de comunidades indígenas del Cauca."),
    ("Transporte y movilidad", "Conexiones a Silvia, Puracé, Coconuco, Tierradentro."),
    ("Institucionalidad", "Alcaldía, Cámara de Comercio del Cauca, oficinas de turismo."),
]
ACTORES_TXT = "\n".join(f"- {n}: {d}" for n, d in ACTORES)

# ----------------------------------------------------------------------------
# BASE DE DATOS (SQLite) — persistencia real de puntos, visitas y eventos
# Soporta el panel de reportes/consultas (Escalabilidad) y gamificación real.
# ----------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raices.db")


def db_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def db_init():
    """Crea las tablas si no existen. Idempotente."""
    with db_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ts        TEXT NOT NULL,
                sesion    TEXT,
                tipo      TEXT NOT NULL,   -- interaccion | mision | recompensa
                pantalla  TEXT,            -- chatbot | robot | mapa
                detalle   TEXT,
                puntos    INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS insignias (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts      TEXT NOT NULL,
                sesion  TEXT,
                nombre  TEXT NOT NULL
            )
        """)
        c.commit()


def registrar_evento(tipo, pantalla="", detalle="", puntos=0):
    """Inserta un evento; nunca rompe la app si la BD falla."""
    try:
        with db_conn() as c:
            c.execute(
                "INSERT INTO eventos (ts, sesion, tipo, pantalla, detalle, puntos) "
                "VALUES (?,?,?,?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"),
                 st.session_state.get("sesion_id", "anon"),
                 tipo, pantalla, detalle, int(puntos)),
            )
            c.commit()
    except Exception as e:
        print("registrar_evento error:", e)


def otorgar_insignia(nombre):
    try:
        with db_conn() as c:
            c.execute(
                "INSERT INTO insignias (ts, sesion, nombre) VALUES (?,?,?)",
                (datetime.datetime.now().isoformat(timespec="seconds"),
                 st.session_state.get("sesion_id", "anon"), nombre),
            )
            c.commit()
    except Exception as e:
        print("otorgar_insignia error:", e)


def puntos_totales(sesion=None):
    try:
        with db_conn() as c:
            if sesion:
                row = c.execute("SELECT COALESCE(SUM(puntos),0) t FROM eventos WHERE sesion=?",
                                (sesion,)).fetchone()
            else:
                row = c.execute("SELECT COALESCE(SUM(puntos),0) t FROM eventos").fetchone()
            return row["t"] or 0
    except Exception:
        return 0


# ----------------------------------------------------------------------------
# API KEYS — se leen desde Secrets de Streamlit (Settings → Secrets)
# ----------------------------------------------------------------------------
def obtener_key():
    try:
        return st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        return ""


def cliente():
    key = obtener_key()
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


def obtener_maps_key():
    try:
        return st.secrets.get("GOOGLE_MAPS_API_KEY", "")
    except Exception:
        return ""


# ----------------------------------------------------------------------------
# GOOGLE MAPS — funciones que llaman a la API real (vía tool use de Claude)
# ----------------------------------------------------------------------------
def _http_get_json(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def maps_buscar_lugares(consulta, cerca_de=""):
    key = obtener_maps_key()
    if not key:
        return "No hay API key de Google Maps configurada."
    # Sesgar siempre la búsqueda hacia Popayán si no especifican otra ciudad.
    if not cerca_de:
        cerca_de = CIUDAD
    texto = f"{consulta} {cerca_de}".strip()
    url = ("https://maps.googleapis.com/maps/api/place/textsearch/json?"
           + urllib.parse.urlencode({"query": texto, "language": "es", "key": key}))
    try:
        data = _http_get_json(url)
    except Exception as e:
        return f"Error al consultar Google Maps: {e}"
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return f"Google Maps respondió: {data.get('status')} {data.get('error_message', '')}"
    resultados = data.get("results", [])[:5]
    if not resultados:
        return "No se encontraron lugares para esa búsqueda."
    lineas = []
    for r in resultados:
        nombre = r.get("name", "Sin nombre")
        dirn = r.get("formatted_address", "")
        rating = r.get("rating")
        abierto = ""
        oh = r.get("opening_hours", {})
        if isinstance(oh, dict) and "open_now" in oh:
            abierto = " · abierto ahora" if oh["open_now"] else " · cerrado ahora"
        cal = f" · ⭐{rating}" if rating else ""
        link = ("https://www.google.com/maps/search/?api=1&query="
                + urllib.parse.quote(f"{nombre} {dirn}"))
        lineas.append(f"{nombre} — {dirn}{cal}{abierto}\n  Mapa: {link}")
    return "\n".join(lineas)


def maps_como_llegar(origen, destino, modo="driving"):
    key = obtener_maps_key()
    if not key:
        return "No hay API key de Google Maps configurada."
    url = ("https://maps.googleapis.com/maps/api/directions/json?"
           + urllib.parse.urlencode({
               "origin": origen, "destination": destino,
               "mode": modo, "language": "es", "key": key}))
    try:
        data = _http_get_json(url)
    except Exception as e:
        return f"Error al consultar Google Maps: {e}"
    if data.get("status") != "OK":
        return f"No se pudo calcular la ruta: {data.get('status')} {data.get('error_message', '')}"
    leg = data["routes"][0]["legs"][0]
    distancia = leg["distance"]["text"]
    duracion = leg["duration"]["text"]
    nombre_modo = {"driving": "en carro", "walking": "a pie",
                   "transit": "en transporte público", "bicycling": "en bici"}.get(modo, modo)
    link = ("https://www.google.com/maps/dir/?api=1&"
            + urllib.parse.urlencode({"origin": origen, "destination": destino,
                                      "travelmode": modo}))
    return (f"Ruta {nombre_modo} de '{leg.get('start_address', origen)}' "
            f"a '{leg.get('end_address', destino)}': {distancia}, "
            f"aprox. {duracion}.\nAbrir en Maps: {link}")


HERRAMIENTAS_MAPS = [
    {
        "name": "buscar_lugares",
        "description": ("Busca lugares reales en Google Maps (restaurantes, cajeros, tiendas, "
                        "hoteles, atracciones, etc.) en Popayán y el Cauca. Úsala cuando el "
                        "turista pregunte dónde encontrar algo o qué hay cerca de un sitio."),
        "input_schema": {
            "type": "object",
            "properties": {
                "consulta": {"type": "string",
                             "description": "Qué buscar, ej: 'empanadas de pipián', 'cajeros automáticos'"},
                "cerca_de": {"type": "string",
                             "description": "Lugar o ciudad de referencia, ej: 'Centro de Popayán'"},
            },
            "required": ["consulta"],
        },
    },
    {
        "name": "como_llegar",
        "description": ("Calcula la ruta y el tiempo entre dos lugares con Google Maps. "
                        "Úsala cuando el turista pregunte cómo llegar de un sitio a otro."),
        "input_schema": {
            "type": "object",
            "properties": {
                "origen": {"type": "string", "description": "Punto de partida"},
                "destino": {"type": "string", "description": "Destino"},
                "modo": {"type": "string", "enum": ["driving", "walking", "transit", "bicycling"],
                         "description": "Medio de transporte (por defecto driving)"},
            },
            "required": ["origen", "destino"],
        },
    },
]


def ejecutar_herramienta(nombre, args):
    if nombre == "buscar_lugares":
        return maps_buscar_lugares(args.get("consulta", ""), args.get("cerca_de", ""))
    if nombre == "como_llegar":
        return maps_como_llegar(args.get("origen", ""), args.get("destino", ""),
                                args.get("modo", "driving"))
    return f"Herramienta desconocida: {nombre}"


def conversar_con_maps(cli, system, mensajes, max_tokens):
    """
    Llama a Claude con las herramientas de Maps y resuelve el ciclo de tool use.
    Devuelve (texto_final, mensajes_actualizados).
    """
    historial = list(mensajes)
    usar_tools = bool(obtener_maps_key())
    for _ in range(5):
        kwargs = dict(model=MODELO_TEXTO, max_tokens=max_tokens,
                      system=system, messages=historial)
        if usar_tools:
            kwargs["tools"] = HERRAMIENTAS_MAPS
        resp = cli.messages.create(**kwargs)

        if resp.stop_reason == "tool_use":
            historial.append({"role": "assistant", "content": resp.content})
            resultados = []
            for bloque in resp.content:
                if bloque.type == "tool_use":
                    salida = ejecutar_herramienta(bloque.name, bloque.input)
                    resultados.append({
                        "type": "tool_result",
                        "tool_use_id": bloque.id,
                        "content": salida,
                    })
            historial.append({"role": "user", "content": resultados})
            continue

        texto = "".join(b.text for b in resp.content if b.type == "text").strip()
        return texto, historial
    return "Lo siento, no pude completar la consulta de mapas.", historial


# ----------------------------------------------------------------------------
# NAVEGACIÓN (estado)
# ----------------------------------------------------------------------------
db_init()

if "sesion_id" not in st.session_state:
    st.session_state.sesion_id = datetime.datetime.now().strftime("s%Y%m%d%H%M%S")
if "pantalla" not in st.session_state:
    st.session_state.pantalla = "inicio"
if "chat_hist" not in st.session_state:
    st.session_state.chat_hist = []
if "robot_hist" not in st.session_state:
    st.session_state.robot_hist = []
if "perfil" not in st.session_state:
    st.session_state.perfil = None
if "misiones_hechas" not in st.session_state:
    st.session_state.misiones_hechas = set()


def ir(p):
    st.session_state.pantalla = p


def perfil_txt():
    p = st.session_state.perfil
    if not p:
        return ""
    tipos = ", ".join(p["tipos"]) if p["tipos"] else "sin preferencia definida"
    return (
        f"\n\nDATOS DEL VIAJERO (úsalos como punto de partida, NO como límite):\n"
        f"- Edad: {p['edad']} años (rango: {p['rango']}).\n"
        f"- Tipo(s) de turismo que mencionó: {tipos}.\n"
        f"Personaliza con esto al inicio, pero atiende con gusto cualquier otra "
        f"petición sobre Popayán y el Cauca (compras, comida, transporte, alojamiento, "
        f"clima, etc.), sin volver a preguntar lo que ya sabes."
    )


# ----------------------------------------------------------------------------
# ESTILOS
# ----------------------------------------------------------------------------
st.markdown("""
<style>
.block-container{max-width:780px}
.stButton>button{
    width:100%; padding:18px; font-size:1.1rem; font-weight:600;
    border-radius:14px; border:1px solid #d9e2db;
}
.titulo-grande{font-size:2.4rem; font-weight:800; text-align:center; color:#1f7a4d; margin:.2em 0}
.sub{text-align:center; color:#6b7a70; margin-bottom:1.2em}
.tarjeta{border:1px solid #d9e2db; border-radius:10px; padding:10px 14px; margin:6px 0; background:#f7f4ee}
.premio{background:#fff8e1; border:2px solid #f2b705; border-radius:14px; padding:18px; text-align:center}
.kpi{background:#eef6f1; border:1px solid #cfe6da; border-radius:12px; padding:14px; text-align:center}
.kpi b{font-size:1.8rem; color:#1f7a4d; display:block}
.impacto{border-left:4px solid #1f7a4d; padding:8px 14px; margin:8px 0; background:#f4faf6}
.historia{background:#fbf7ef; border:1px solid #e6dcc4; border-left:5px solid #f2b705;
          border-radius:12px; padding:16px 18px; margin-top:14px; line-height:1.55; font-size:.95rem}
.historia-tit{font-weight:700; color:#8a6d1f; margin-bottom:8px; font-size:1.05rem}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# BARRA LATERAL
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🌿 Raíces de Paz IA")

    faltantes = []
    if not obtener_key():
        faltantes.append("ANTHROPIC_API_KEY")
    if not obtener_maps_key():
        faltantes.append("GOOGLE_MAPS_API_KEY")

    if not faltantes:
        st.success("Servicios conectados ✓")
    else:
        st.caption("⚠️ Falta en Secrets: " + ", ".join(faltantes))

    st.divider()
    st.metric("🌿 Tus puntos Raíces", puntos_totales(st.session_state.sesion_id))
    if st.session_state.pantalla != "inicio":
        st.button("🏠 Volver al menú", on_click=ir, args=("menu",))


# ============================================================================
# PANTALLA: INICIO
# ============================================================================
def pantalla_inicio():
    st.markdown('<div class="titulo-grande">🌿 Raíces de Paz IA</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Popayán turística inteligente · IA para un destino competitivo y sostenible</div>',
                unsafe_allow_html=True)
    st.write("")
    st.markdown(
        '<div class="tarjeta">Asistente con IA que <b>promociona los atractivos de Popayán</b>, '
        '<b>articula a los actores del ecosistema</b> turístico y <b>eleva la cultura de servicio</b> '
        'al visitante — con chatbot, robot guía por voz, misiones de exploración y reportes.</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.button("▶  Iniciar", on_click=ir, args=("perfil",))


# ============================================================================
# PANTALLA: PERFIL
# ============================================================================
TIPOS_TURISMO = [
    "Cultural e histórico", "Religioso (Semana Santa)", "Gastronómico",
    "Naturaleza y ecoturismo", "Aventura y senderismo", "Comunitario e indígena",
    "Termales y bienestar", "Fotografía y paisajes",
]


def pantalla_perfil():
    st.markdown('<div class="titulo-grande">Antes de empezar</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Cuéntanos un poco de ti para personalizar tu visita a Popayán</div>',
                unsafe_allow_html=True)

    edad = st.slider("¿Cuántos años tienes?", min_value=5, max_value=99, value=25)
    tipos = st.multiselect(
        "¿Qué tipo de turismo te interesa en Popayán? (elige uno o varios)",
        TIPOS_TURISMO,
        help="Esto le da contexto a la IA para recomendarte mejor.",
    )

    st.write("")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if st.button("Continuar  ▶"):
            if not tipos:
                st.warning("Elige al menos un tipo de turismo para continuar.")
            else:
                rango = ("niño/a" if edad < 13 else "adolescente" if edad < 18
                         else "adulto joven" if edad < 36 else "adulto" if edad < 60
                         else "adulto mayor")
                st.session_state.perfil = {"edad": edad, "rango": rango, "tipos": tipos}
                registrar_evento("interaccion", "perfil",
                                 f"edad={edad}; tipos={'|'.join(tipos)}")
                ir("menu")
                st.rerun()


# ============================================================================
# PANTALLA: MENÚ
# ============================================================================
def pantalla_menu():
    st.markdown('<div class="titulo-grande">Elige una experiencia</div>', unsafe_allow_html=True)
    p = st.session_state.perfil
    if p:
        st.markdown(f'<div class="sub">Perfil: {p["edad"]} años · {", ".join(p["tipos"])}</div>',
                    unsafe_allow_html=True)
    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        st.button("🗺️  Mapa / Misiones", on_click=ir, args=("mapa",))
        st.button("💬  Chatbot", on_click=ir, args=("chatbot",))
        st.button("🤝  Actores del turismo", on_click=ir, args=("actores",))
    with c2:
        st.button("🤖  Robot ROBI (voz)", on_click=ir, args=("robot",))
        st.button("📊  Reportes", on_click=ir, args=("reportes",))
        st.button("🥽  AR — Próximamente", on_click=ir, args=("ar",))


# ============================================================================
# PANTALLA: CHATBOT
# ============================================================================
SYSTEM_CHAT = f"""Eres "Raíces", un guía experto en turismo de {CIUDAD} y sus alrededores. Tu misión es promocionar los atractivos de Popayán, ayudar a articular al visitante con los actores locales (operadores, restaurantes, hoteles, artesanos) y dar un servicio cálido y excelente.

Atractivos destacados de Popayán y el Cauca (referencia central, da prioridad a estos):
{CATALOGO_TXT}

Actores del ecosistema que puedes ayudar a identificar y conectar:
{ACTORES_TXT}

Reglas:
- Responde en español, cálido y conciso. Céntrate en Popayán y el Cauca.
- Si te preguntan por otras regiones de Colombia, ayuda, pero recuerda con gracia que tu especialidad es Popayán.
- Para peticiones prácticas ("¿dónde como empanadas de pipián?", "¿cómo llego de Popayán a Silvia?"), usa las herramientas de Google Maps y entrega lugares y rutas reales con sus enlaces de Maps.
- Para no inventar datos sensibles (horarios o precios exactos), si no estás seguro, dilo y sugiere confirmar con el lugar o usa la búsqueda de Maps.
- Sugiere 2 o 3 opciones máximo por respuesta y explica por qué encajan.
- Si falta info clave (días, presupuesto, con quién viaja), haz UNA sola pregunta.
- Resalta el impacto social, cultural y ambiental positivo del turismo comunitario cuando sea relevante."""


def pantalla_chatbot():
    st.markdown('<div class="titulo-grande">💬 Chatbot</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Tu guía de Popayán: atractivos, comida, rutas y más</div>',
                unsafe_allow_html=True)

    cli = cliente()
    if cli is None:
        st.error("Falta la API key de Claude en Secrets para conversar.")
        return

    for m in st.session_state.chat_hist:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.write(m["content"])

    prompt = st.chat_input("Ej: ¿dónde pruebo empanadas de pipián? o ¿cómo llego de Popayán a Silvia?")
    if prompt:
        st.session_state.chat_hist.append({"role": "user", "content": prompt})
        registrar_evento("interaccion", "chatbot", prompt[:200], puntos=5)
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Raíces está pensando…"):
                try:
                    texto, _ = conversar_con_maps(
                        cli, SYSTEM_CHAT + perfil_txt(),
                        st.session_state.chat_hist, max_tokens=900,
                    )
                except Exception as e:
                    texto = f"❌ Error al conectar con la API: {e}"
            st.write(texto)
        st.session_state.chat_hist.append({"role": "assistant", "content": texto})
        st.rerun()


# ============================================================================
# PANTALLA: ROBOT (voz por navegador)
# ============================================================================
SYSTEM_ROBOT = f"""Eres "ROBI", un robot guía de turismo de {CIUDAD} que habla en voz alta.
Como tu respuesta será leída en voz alta, sé breve y natural: máximo 4 o 5 frases, sin listas, sin asteriscos, sin emojis, sin URLs.
Promocionas los atractivos de Popayán y ayudas con peticiones prácticas (comida típica como empanadas de pipián o carantanta, transporte a Silvia o Puracé, alojamiento, clima).
Tienes herramientas de Google Maps para buscar lugares y calcular cómo llegar; úsalas cuando el turista lo pida. Como tu respuesta se escucha, NUNCA leas enlaces ni URLs: resume dirección, distancia y tiempo con palabras.
El perfil del viajero es un punto de partida, no un límite.
Atractivos: {", ".join(n for n, _, _ in SITIOS)}.
Si falta información, haz una sola pregunta corta."""


def hablar_en_navegador(texto):
    texto_js = json.dumps(texto)
    html = f"""
    <script>
    function hablar() {{
      const u = new SpeechSynthesisUtterance({texto_js});
      u.lang = 'es-ES'; u.rate = 1; u.pitch = 1;
      const voces = window.speechSynthesis.getVoices().filter(v => v.lang.startsWith('es'));
      if(voces.length) u.voice = voces[0];
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    }}
    if (window.speechSynthesis.getVoices().length) {{
      hablar();
    }} else {{
      window.speechSynthesis.onvoiceschanged = hablar;
    }}
    </script>
    """
    components.html(html, height=0)


def pantalla_robot():
    st.markdown('<div class="titulo-grande">🤖 Robot ROBI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Háblale por voz; te responde hablando</div>', unsafe_allow_html=True)

    cli = cliente()
    if cli is None:
        st.error("Falta la API key de Claude en Secrets para usar el robot.")
        return

    st.info("🎙️ Pulsa **🎤 Grabar**, di tu pregunta, vuelve a pulsar para parar, "
            "y ROBI te responderá en voz alta. Usa Chrome o Edge.")

    texto_voz = speech_to_text(
        language="es", start_prompt="🎤 Grabar", stop_prompt="⏹️ Detener",
        just_once=True, use_container_width=True, key="stt_robi",
    )
    texto = st.text_input("O escríbelo aquí:", key="robot_input")
    enviar = st.button("Enviar a ROBI")

    for m in st.session_state.robot_hist:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.write(m["content"])

    mensaje = None
    if texto_voz:
        mensaje = texto_voz.strip()
    elif enviar and texto.strip():
        mensaje = texto.strip()

    if mensaje:
        st.session_state.robot_hist.append({"role": "user", "content": mensaje})
        registrar_evento("interaccion", "robot", mensaje[:200], puntos=5)
        with st.chat_message("user"):
            st.write(mensaje)
        with st.spinner("ROBI está pensando…"):
            try:
                salida, _ = conversar_con_maps(
                    cli, SYSTEM_ROBOT + perfil_txt(),
                    st.session_state.robot_hist, max_tokens=400,
                )
            except Exception as e:
                salida = f"Hubo un error al conectar: {e}"
        st.session_state.robot_hist.append({"role": "assistant", "content": salida})
        with st.chat_message("assistant"):
            st.write(salida)
        hablar_en_navegador(salida)


# ============================================================================
# PANTALLA: ACTORES DEL ECOSISTEMA (objetivo 2 del reto: articulación)
# ============================================================================
def pantalla_actores():
    st.markdown('<div class="titulo-grande">🤝 Actores del turismo</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Identifica y conecta con el ecosistema turístico de Popayán</div>',
                unsafe_allow_html=True)

    for nombre, desc in ACTORES:
        st.markdown(f'<div class="tarjeta"><b>{nombre}</b><br>{desc}</div>', unsafe_allow_html=True)

    st.write("")
    st.markdown("#### 🔎 Busca un actor o servicio cerca")
    consulta = st.text_input("¿Qué necesitas?",
                             placeholder="Ej: hoteles boutique, guías de Semana Santa, artesanías misak")
    if st.button("Buscar en Popayán"):
        if not obtener_maps_key():
            st.warning("Falta GOOGLE_MAPS_API_KEY en Secrets para la búsqueda en vivo.")
        elif consulta.strip():
            with st.spinner("Buscando actores y servicios…"):
                resultado = maps_buscar_lugares(consulta.strip(), "Popayán, Cauca")
            registrar_evento("interaccion", "actores", consulta[:200], puntos=5)
            for linea in resultado.split("\n"):
                if linea.strip():
                    st.write(linea)
        else:
            st.info("Escribe qué actor o servicio buscas.")


# ============================================================================
# PANTALLA: MAPA / MISIONES (subir imagen → Claude detecta → recompensa)
# ============================================================================
# Misiones reales de Popayán. Cada una: clave, etiqueta, objetivo de detección,
# insignia y puntos. La detección la valida Claude con visión.
MISIONES = {
    "humilladero": {
        "etiqueta": "Puente del Humilladero",
        "objetivo": "el Puente del Humilladero de Popayán (puente colonial de ladrillo con arcos)",
        "insignia": "Guardián del Humilladero",
        "puntos": 100,
        "lat": 2.44430, "lng": -76.60530, "emoji": "🌉",
    },
    "torre": {
        "etiqueta": "Torre del Reloj",
        "objetivo": "la Torre del Reloj de Popayán (torre colonial blanca con un reloj)",
        "insignia": "Vigía del Tiempo",
        "puntos": 100,
        "lat": 2.44120, "lng": -76.60670, "emoji": "🕰️",
    },
    "empanadas": {
        "etiqueta": "Empanadas de pipián",
        "objetivo": "empanadas de pipián (empanadas pequeñas fritas, típicas de Popayán, servidas con ají de maní)",
        "insignia": "Sabor Payanés",
        "puntos": 80,
        "lat": 2.44060, "lng": -76.60590, "emoji": "🥟",
    },
    "ciudad_blanca": {
        "etiqueta": "Fachada blanca colonial",
        "objetivo": "una fachada colonial blanca del centro histórico de Popayán (la Ciudad Blanca)",
        "insignia": "Explorador de la Ciudad Blanca",
        "puntos": 80,
        "lat": 2.44200, "lng": -76.60750, "emoji": "🏛️",
    },
}


def system_vision(objetivo):
    return f"""Eres el validador de misiones de una app de turismo en Popayán, Colombia.
El jugador debe encontrar y fotografiar este objetivo: {objetivo}.

Analiza la imagen y responde ÚNICAMENTE en este formato exacto:
DETECTADO: SI    (si el objetivo aparece claramente)
o
DETECTADO: NO    (si no aparece)
Luego, en una línea aparte, una frase corta (máx 20 palabras) explicando qué ves."""


def historia_del_lugar(cli, etiqueta):
    """Genera (y cachea) una pequeña historia cultural del lugar, adaptada al perfil.
    Se guarda en session_state para no volver a llamar a la API en cada recarga."""
    cache = st.session_state.setdefault("historias", {})
    if etiqueta in cache:
        return cache[etiqueta]

    system = (
        "Eres un narrador cultural experto en Popayán y el Cauca, Colombia. "
        "Cuentas historias breves, cálidas y rigurosas: datos reales de historia, "
        "cultura, arquitectura, tradiciones y gastronomía, sin inventar fechas ni cifras. "
        "Si no estás seguro de un dato exacto, habla en términos generales en vez de inventar."
        + perfil_txt()
    )
    prompt = (
        f"El viajero acaba de completar una misión visitando: {etiqueta} (Popayán, Cauca). "
        "Escríbele una pequeña historia del lugar (130-180 palabras), en español, en 2 o 3 "
        "párrafos cortos. Incluye su origen o historia, su valor cultural y un dato curioso "
        "o tradición local que lo haga memorable. Tono de guía apasionado pero cercano. "
        "No uses listas ni títulos, solo prosa. No repitas literalmente el nombre en cada frase."
    )
    try:
        resp = cli.messages.create(
            model=MODELO_TEXTO, max_tokens=500, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        texto = f"(No se pudo cargar la historia en este momento: {e})"
    cache[etiqueta] = texto
    return texto


def mapa_popayan_html():
    """Mapa real de Popayán (Leaflet) con personaje arrastrable y los 4 POIs.
    Al soltar el personaje cerca de un pin, recarga la página padre con ?mision=clave."""
    pois = [
        {"clave": k, "lat": m["lat"], "lng": m["lng"],
         "nombre": m["etiqueta"], "emoji": m["emoji"], "puntos": m["puntos"],
         "hecha": k in st.session_state.misiones_hechas}
        for k, m in MISIONES.items()
    ]
    pois_js = json.dumps(pois)
    # Centro del casco histórico de Popayán
    centro_lat, centro_lng = 2.4419, -76.6063
    html = f"""
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
      #mapa-pop{{height:440px;border-radius:16px;border:2px solid #cfe6da;overflow:hidden}}
      .instru-pop{{font-size:.86rem;color:#5b3a8c;background:#efe9f7;padding:8px 12px;
                   border-radius:8px;margin-bottom:8px}}
      .estado-pop{{font-size:.9rem;font-weight:600;color:#1f7a4d;text-align:center;
                   margin-top:8px;min-height:20px}}
      .jug-icon{{font-size:26px;line-height:38px;text-align:center;
                 filter:drop-shadow(0 3px 4px rgba(0,0,0,.4));cursor:grab}}
      .poi-icon{{font-size:24px;line-height:30px;text-align:center;
                 filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))}}
      .poi-label{{background:rgba(255,255,255,.9);border-radius:6px;padding:1px 6px;
                  font-size:11px;font-weight:600;white-space:nowrap}}
    </style>
    <div class="instru-pop">👆 Arrastra el explorador 🧍 y suéltalo sobre un pin para abrir la misión.
       Funciona con mouse y con el dedo.</div>
    <div id="mapa-pop"></div>
    <div class="estado-pop" id="estado-pop">Arrastra tu personaje hacia un destino…</div>
    <script>
      const POIS = {pois_js};
      const map = L.map('mapa-pop', {{zoomControl:true, scrollWheelZoom:false}})
                   .setView([{centro_lat}, {centro_lng}], 16);
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        maxZoom: 19, attribution: '© OpenStreetMap'
      }}).addTo(map);

      // Pines de misiones
      const marcadores = [];
      POIS.forEach(p => {{
        const icon = L.divIcon({{
          className:'', html:`<div class="poi-icon">${{p.hecha?'✅':p.emoji}}📍</div>`
                              +`<div class="poi-label">${{p.nombre}}</div>`,
          iconSize:[30,44], iconAnchor:[15,30]
        }});
        const mk = L.marker([p.lat, p.lng], {{icon}}).addTo(map);
        mk.on('click', () => abrirMision(p));
        marcadores.push(mk);
      }});

      // Personaje arrastrable: parte del centro
      const jugIcon = L.divIcon({{className:'', html:'<div class="jug-icon">🧍</div>',
                                  iconSize:[38,38], iconAnchor:[19,19]}});
      const jugador = L.marker([{centro_lat}, {centro_lng}],
                               {{icon:jugIcon, draggable:true}}).addTo(map);

      const estado = document.getElementById('estado-pop');

      function distM(a, b) {{ return map.distance(a, b); }}  // metros

      jugador.on('dragstart', () => {{ estado.textContent = 'Explorando…'; }});
      jugador.on('dragend', () => {{
        const pos = jugador.getLatLng();
        let cerca = null, min = 60;  // umbral 60 m
        POIS.forEach(p => {{
          const d = distM(pos, L.latLng(p.lat, p.lng));
          if (d < min) {{ min = d; cerca = p; }}
        }});
        if (cerca) {{
          estado.textContent = '¡Llegaste a ' + cerca.nombre + '! Abriendo misión…';
          abrirMision(cerca);
        }} else {{
          estado.textContent = 'Sigue arrastrando hacia un pin 📍';
        }}
      }});

      function abrirMision(p) {{
        try {{
          const url = new URL(window.parent.location.href);
          url.searchParams.set('mision', p.clave);
          window.parent.location.href = url.toString();
        }} catch(e) {{
          estado.textContent = 'Selecciona la misión "' + p.nombre + '" abajo para subir tu foto.';
        }}
      }}
    </script>
    """
    return html


def pantalla_mapa():
    st.markdown('<div class="titulo-grande">🗺️ Mapa explorador</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Recorre el centro histórico de Popayán y completa misiones</div>',
                unsafe_allow_html=True)

    cli = cliente()
    if cli is None:
        st.error("Falta la API key de Claude en Secrets para validar misiones.")
        return

    # Mapa real interactivo de Popayán
    components.html(mapa_popayan_html(), height=540)

    # ¿El jugador soltó el personaje sobre un pin? Llega como ?mision=clave
    mision_param = st.query_params.get("mision")
    claves = list(MISIONES.keys())
    idx_default = claves.index(mision_param) if mision_param in MISIONES else 0

    sel = st.selectbox(
        "Misión seleccionada:",
        claves, index=idx_default,
        format_func=lambda k: ("✅ " if k in st.session_state.misiones_hechas else "🎯 ")
                               + MISIONES[k]["etiqueta"],
    )
    mision = MISIONES[sel]
    st.markdown(f"**🎯 Misión:** encuentra y sube una foto de **{mision['etiqueta']}** "
                f"({mision['puntos']} puntos).")

    if sel in st.session_state.misiones_hechas:
        st.success(f"Ya completaste esta misión. Insignia: {mision['insignia']} 🏅")

    archivo = st.file_uploader("Sube tu foto", type=["jpg", "jpeg", "png", "webp"])
    if archivo:
        st.image(archivo, caption="Tu captura", use_container_width=True)
        if st.button("🔍 Validar misión"):
            datos = archivo.getvalue()
            b64 = base64.standard_b64encode(datos).decode("utf-8")
            tipo = archivo.type or "image/jpeg"
            if tipo == "image/jpg":
                tipo = "image/jpeg"
            with st.spinner("Claude está revisando tu imagen…"):
                try:
                    resp = cli.messages.create(
                        model=MODELO_VISION, max_tokens=200,
                        system=system_vision(mision["objetivo"]),
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "image",
                                 "source": {"type": "base64", "media_type": tipo, "data": b64}},
                                {"type": "text", "text": "¿Aparece el objetivo de la misión?"},
                            ],
                        }],
                    )
                    salida = "".join(b.text for b in resp.content if b.type == "text").strip()
                except Exception as e:
                    salida = f"DETECTADO: NO\nError al analizar: {e}"

            detectado = "DETECTADO: SI" in salida.upper()
            comentario = salida.split("\n", 1)[1].strip() if "\n" in salida else ""

            if detectado:
                ya = sel in st.session_state.misiones_hechas
                st.balloons()
                if not ya:
                    st.session_state.misiones_hechas.add(sel)
                    registrar_evento("mision", "mapa", mision["etiqueta"], puntos=mision["puntos"])
                    otorgar_insignia(mision["insignia"])
                st.markdown(
                    f'<div class="premio">🏆 <b>¡Misión cumplida!</b><br>{comentario}'
                    f'<br><br>Recompensa: <b>+{mision["puntos"]} puntos Raíces</b> 🌿<br>'
                    f'Insignia: <b>{mision["insignia"]}</b>'
                    + ("<br><small>(ya la tenías; no se suman puntos de nuevo)</small>" if ya else "")
                    + '</div>',
                    unsafe_allow_html=True,
                )
                # Pequeña historia cultural del lugar, generada por Claude
                with st.spinner("Descubriendo la historia de este lugar…"):
                    historia = historia_del_lugar(cli, mision["etiqueta"])
                st.markdown(
                    f'<div class="historia"><div class="historia-tit">📖 La historia de '
                    f'{mision["etiqueta"]}</div>{historia}</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.warning(f"Aún no detecto el objetivo. {comentario}")
                st.caption("Inténtalo con otra foto donde el objetivo se vea claro.")


# ============================================================================
# PANTALLA: REPORTES (Escalabilidad — reportes y consultas)
# ============================================================================
def pantalla_reportes():
    st.markdown('<div class="titulo-grande">📊 Reportes</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Datos de uso para gestionar el destino turístico</div>',
                unsafe_allow_html=True)

    try:
        with db_conn() as c:
            tot_inter = c.execute("SELECT COUNT(*) n FROM eventos WHERE tipo='interaccion'").fetchone()["n"]
            tot_mis = c.execute("SELECT COUNT(*) n FROM eventos WHERE tipo='mision'").fetchone()["n"]
            tot_pts = c.execute("SELECT COALESCE(SUM(puntos),0) t FROM eventos").fetchone()["t"]
            por_pantalla = c.execute(
                "SELECT pantalla, COUNT(*) n FROM eventos WHERE tipo='interaccion' "
                "AND pantalla<>'' GROUP BY pantalla ORDER BY n DESC").fetchall()
            top_misiones = c.execute(
                "SELECT detalle, COUNT(*) n FROM eventos WHERE tipo='mision' "
                "GROUP BY detalle ORDER BY n DESC").fetchall()
            insignias = c.execute(
                "SELECT nombre, COUNT(*) n FROM insignias GROUP BY nombre ORDER BY n DESC").fetchall()
            recientes = c.execute(
                "SELECT ts, pantalla, tipo, detalle, puntos FROM eventos "
                "ORDER BY id DESC LIMIT 15").fetchall()
    except Exception as e:
        st.error(f"No se pudo leer la base de datos: {e}")
        return

    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="kpi"><b>{tot_inter}</b>interacciones IA</div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="kpi"><b>{tot_mis}</b>misiones completadas</div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="kpi"><b>{tot_pts}</b>puntos otorgados</div>', unsafe_allow_html=True)

    st.write("")
    st.markdown("#### Uso por experiencia")
    if por_pantalla:
        st.bar_chart({r["pantalla"]: r["n"] for r in por_pantalla})
    else:
        st.caption("Aún no hay interacciones registradas.")

    st.markdown("#### Atractivos más visitados (misiones)")
    if top_misiones:
        for r in top_misiones:
            st.write(f"- {r['detalle']}: {r['n']} vez/veces")
    else:
        st.caption("Aún no se completan misiones.")

    st.markdown("#### Insignias otorgadas")
    if insignias:
        st.write(" · ".join(f"{r['nombre']} ({r['n']})" for r in insignias))
    else:
        st.caption("Aún no hay insignias.")

    st.markdown("#### Actividad reciente")
    if recientes:
        st.dataframe(
            [{"Fecha": r["ts"], "Experiencia": r["pantalla"] or r["tipo"],
              "Tipo": r["tipo"], "Detalle": (r["detalle"] or "")[:60], "Puntos": r["puntos"]}
             for r in recientes],
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("Sin actividad todavía. Usa el chatbot, el robot o el mapa para generar datos.")

    st.divider()
    st.markdown("#### 🌎 Impacto del proyecto")
    st.markdown(
        '<div class="impacto"><b>Social:</b> da visibilidad a guías, artesanos misak y cocineras '
        'tradicionales, distribuyendo el flujo de visitantes hacia actores locales.</div>'
        '<div class="impacto"><b>Económico:</b> mayor digitalización y articulación elevan la '
        'competitividad del destino y el gasto del turista en comercio local.</div>'
        '<div class="impacto"><b>Ambiental:</b> promueve termales, senderos y turismo comunitario '
        'sostenible frente al turismo masivo no regulado.</div>'
        '<div class="impacto"><b>Cultural:</b> difunde la Semana Santa (Patrimonio UNESCO), la cocina '
        'payanesa (Ciudad Creativa de la Gastronomía) y el legado colonial.</div>',
        unsafe_allow_html=True,
    )


# ============================================================================
# PANTALLA: AR (no disponible)
# ============================================================================
def pantalla_ar():
    st.markdown('<div class="titulo-grande">🥽 Realidad Aumentada</div>', unsafe_allow_html=True)
    st.info("🚧 **Próximamente** — recorridos AR sobre las fachadas coloniales y las "
            "procesiones de Semana Santa. Parte del roadmap del proyecto.")


# ============================================================================
# RUTEADOR
# ============================================================================
P = st.session_state.pantalla
if P == "inicio":
    pantalla_inicio()
elif P == "perfil":
    pantalla_perfil()
elif P == "menu":
    pantalla_menu()
elif P == "chatbot":
    pantalla_chatbot()
elif P == "robot":
    pantalla_robot()
elif P == "actores":
    pantalla_actores()
elif P == "mapa":
    pantalla_mapa()
elif P == "reportes":
    pantalla_reportes()
elif P == "ar":
    pantalla_ar()
