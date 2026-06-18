"""
Raíces de Paz IA — App de demostración (Streamlit)
Etapas: Chatbot · Robot guía por voz · Mapa explorador con detección de imagen · AR (próximamente)

La API key de Claude se lee de forma segura desde st.secrets["ANTHROPIC_API_KEY"]
(en Streamlit Cloud: menú ⋮ → Settings → Secrets).
Para correr en local sin secrets, también acepta una key escrita en la barra lateral.
"""

import base64
import streamlit as st
import streamlit.components.v1 as components
import anthropic

# ----------------------------------------------------------------------------
# CONFIGURACIÓN GENERAL
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Raíces de Paz IA", page_icon="🌿", layout="centered")

MODELO = "claude-sonnet-4-6"

# Catálogo de destinos reales de Colombia (compartido por chatbot y robot)
SITIOS = [
    ("Caño Cristales", "La Macarena, Meta", "El río de los cinco colores"),
    ("Ciudad Perdida (Teyuna)", "Sierra Nevada de Santa Marta", "Trekking y arqueología indígena"),
    ("Salento y Valle de Cocora", "Quindío", "Café, palma de cera y senderismo"),
    ("Cartagena de Indias", "Bolívar", "Historia, patrimonio UNESCO y playa"),
    ("Cabo de la Vela", "La Guajira", "Desierto, cultura wayúu y mar"),
    ("Mompox", "Bolívar", "Pueblo colonial y filigrana"),
    ("Guatapé y El Peñol", "Antioquia", "Mirador, zócalos y embalse"),
    ("San Agustín", "Huila", "Estatuaria precolombina, UNESCO"),
    ("Amazonas (Leticia y Puerto Nariño)", "Amazonas", "Selva, comunidades y delfines rosados"),
    ("Barichara", "Santander", "Pueblo de piedra y Camino Real"),
    ("Nuquí y Bahía Solano", "Chocó", "Pacífico, ballenas y turismo comunitario"),
    ("Villa de Leyva", "Boyacá", "Colonial, fósiles y cielo estrellado"),
]
CATALOGO_TXT = "\n".join(f"- {n} ({r}): {t}" for n, r, t in SITIOS)


# ----------------------------------------------------------------------------
# API KEY
# ----------------------------------------------------------------------------
def obtener_key():
    # 1) Secrets de Streamlit Cloud (recomendado)
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    # 2) Key escrita manualmente (para pruebas locales)
    return st.session_state.get("api_key_manual", "")


def cliente():
    key = obtener_key()
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


# ----------------------------------------------------------------------------
# NAVEGACIÓN (estado)
# ----------------------------------------------------------------------------
if "pantalla" not in st.session_state:
    st.session_state.pantalla = "inicio"
if "chat_hist" not in st.session_state:
    st.session_state.chat_hist = []
if "robot_hist" not in st.session_state:
    st.session_state.robot_hist = []
if "recompensa_dada" not in st.session_state:
    st.session_state.recompensa_dada = False
if "perfil" not in st.session_state:
    st.session_state.perfil = None  # se llena en la pantalla de perfil


def ir(p):
    st.session_state.pantalla = p


def perfil_txt():
    """Resumen del perfil del viajero para inyectar en los prompts de Claude."""
    p = st.session_state.perfil
    if not p:
        return ""
    tipos = ", ".join(p["tipos"]) if p["tipos"] else "sin preferencia definida"
    return (
        f"\n\nDATOS DEL VIAJERO (úsalos para personalizar desde el inicio):\n"
        f"- Edad: {p['edad']} años (rango: {p['rango']}).\n"
        f"- Tipo(s) de turismo que busca: {tipos}.\n"
        f"Ajusta el tono y las recomendaciones a este perfil sin volver a preguntar lo que ya sabes."
    )


# ----------------------------------------------------------------------------
# ESTILOS
# ----------------------------------------------------------------------------
st.markdown("""
<style>
.block-container{max-width:760px}
.stButton>button{
    width:100%; padding:18px; font-size:1.1rem; font-weight:600;
    border-radius:14px; border:1px solid #d9e2db;
}
.titulo-grande{font-size:2.4rem; font-weight:800; text-align:center; color:#1f7a4d; margin:.2em 0}
.sub{text-align:center; color:#6b7a70; margin-bottom:1.5em}
.tarjeta-sitio{border:1px solid #d9e2db; border-radius:10px; padding:10px 14px; margin:6px 0; background:#f7f4ee}
.premio{background:#fff8e1; border:2px solid #f2b705; border-radius:14px; padding:18px; text-align:center}
</style>
""", unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# BARRA LATERAL — key manual para pruebas locales + estado
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Configuración")
    if obtener_key():
        st.success("API key conectada")
    else:
        st.warning("Sin API key")
        st.text_input(
            "API key de Claude (solo para pruebas locales)",
            type="password", key="api_key_manual",
            help="En Streamlit Cloud usa Settings → Secrets en lugar de esto.",
        )
    st.caption("Para subir a la nube, guarda la key en Secrets como ANTHROPIC_API_KEY.")
    st.divider()
    if st.session_state.pantalla != "inicio":
        st.button("🏠 Volver al menú", on_click=ir, args=("menu",))


# ============================================================================
# PANTALLA: INICIO
# ============================================================================
def pantalla_inicio():
    st.markdown('<div class="titulo-grande">🌿 Raíces de Paz IA</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Turismo comunitario inteligente por Colombia</div>', unsafe_allow_html=True)
    st.write("")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.button("▶  Iniciar", on_click=ir, args=("perfil",))


# ============================================================================
# PANTALLA: PERFIL (edad + tipo de turismo) — antes del menú
# ============================================================================
TIPOS_TURISMO = [
    "Naturaleza y ecoturismo", "Cultural e histórico", "Aventura y adrenalina",
    "Gastronómico", "Playa y descanso", "Comunitario e indígena",
    "Café y rural", "Fotografía y paisajes",
]


def pantalla_perfil():
    st.markdown('<div class="titulo-grande">Antes de empezar</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Cuéntanos un poco de ti para personalizar tu experiencia</div>',
                unsafe_allow_html=True)

    edad = st.slider("¿Cuántos años tienes?", min_value=5, max_value=99, value=25)
    tipos = st.multiselect(
        "¿Qué tipo de turismo quieres hacer? (elige uno o varios)",
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
                ir("menu")
                st.rerun()


# ============================================================================
# PANTALLA: MENÚ
# ============================================================================
def pantalla_menu():
    st.markdown('<div class="titulo-grande">Elige una experiencia</div>', unsafe_allow_html=True)
    p = st.session_state.perfil
    if p:
        st.markdown(
            f'<div class="sub">Perfil: {p["edad"]} años · {", ".join(p["tipos"])}</div>',
            unsafe_allow_html=True,
        )
    st.write("")
    c1, c2 = st.columns(2)
    with c1:
        st.button("🗺️  Mapa", on_click=ir, args=("mapa",))
        st.button("💬  Chatbot", on_click=ir, args=("chatbot",))
    with c2:
        st.button("🤖  Robot", on_click=ir, args=("robot",))
        st.button("🥽  AR — No disponible", on_click=ir, args=("ar",))


# ============================================================================
# PANTALLA: CHATBOT (texto)
# ============================================================================
SYSTEM_CHAT = f"""Eres "Raíces", un guía de turismo comunitario en Colombia. Recomiendas rutas y destinos según los gustos, presupuesto y tiempo del viajero, priorizando experiencias locales y sostenibles.

Catálogo disponible:
{CATALOGO_TXT}

Reglas:
- Responde en español, cálido y conciso.
- Explica por qué cada destino encaja con lo que pidió la persona.
- Sugiere 2 o 3 destinos máximo por respuesta.
- Si falta info (días, presupuesto, con quién viaja), haz UNA pregunta para afinar.
- Resalta el impacto social y ambiental positivo cuando sea relevante."""


def pantalla_chatbot():
    st.markdown('<div class="titulo-grande">💬 Chatbot</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Cuéntame tus gustos y te sugiero destinos</div>', unsafe_allow_html=True)

    cli = cliente()
    if cli is None:
        st.error("Configura tu API key (barra lateral o Secrets) para conversar.")
        return

    for m in st.session_state.chat_hist:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.write(m["content"])

    prompt = st.chat_input("Ej: me gusta la naturaleza y el café, 5 días, presupuesto medio")
    if prompt:
        st.session_state.chat_hist.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Raíces está pensando…"):
                try:
                    resp = cli.messages.create(
                        model=MODELO, max_tokens=900, system=SYSTEM_CHAT + perfil_txt(),
                        messages=st.session_state.chat_hist,
                    )
                    texto = "".join(b.text for b in resp.content if b.type == "text")
                except Exception as e:
                    texto = f"❌ Error al conectar con la API: {e}"
            st.write(texto)
        st.session_state.chat_hist.append({"role": "assistant", "content": texto})


# ============================================================================
# PANTALLA: ROBOT (voz por navegador)
# ============================================================================
SYSTEM_ROBOT = f"""Eres "ROBI", un robot guía de turismo comunitario en Colombia que habla en voz alta.
Como tu respuesta será leída en voz alta, sé breve y natural: máximo 4 o 5 frases, sin listas, sin asteriscos, sin emojis, sin URLs.
Recomiendas destinos según los gustos del viajero, priorizando experiencias locales y sostenibles.
Catálogo: {", ".join(n for n, _, _ in SITIOS)}.
Si falta información, haz una sola pregunta corta."""


def pantalla_robot():
    st.markdown('<div class="titulo-grande">🤖 Robot ROBI</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Háblale por voz; te responde hablando</div>', unsafe_allow_html=True)

    cli = cliente()
    if cli is None:
        st.error("Configura tu API key (barra lateral o Secrets) para usar el robot.")
        return

    st.info("🎙️ Pulsa **Hablar**, di tu pregunta y ROBI te responderá en voz alta. "
            "Usa Chrome o Edge. Si la voz falla, escribe abajo como respaldo.")

    # --- Componente de voz en el navegador (reconocimiento + síntesis) ---
    # Captura la voz, la transcribe con Web Speech, y rellena el campo de texto de Streamlit.
    componente_voz()

    # Campo de respaldo / receptor del texto transcrito
    texto = st.text_input("Tu mensaje (se llena solo al hablar, o escríbelo):", key="robot_input")
    enviar = st.button("Enviar a ROBI")

    # Mostrar historial
    for m in st.session_state.robot_hist:
        with st.chat_message("user" if m["role"] == "user" else "assistant"):
            st.write(m["content"])

    if enviar and texto.strip():
        st.session_state.robot_hist.append({"role": "user", "content": texto.strip()})
        with st.spinner("ROBI está pensando…"):
            try:
                resp = cli.messages.create(
                    model=MODELO, max_tokens=400, system=SYSTEM_ROBOT + perfil_txt(),
                    messages=st.session_state.robot_hist,
                )
                salida = "".join(b.text for b in resp.content if b.type == "text").strip()
            except Exception as e:
                salida = f"Hubo un error al conectar: {e}"
        st.session_state.robot_hist.append({"role": "assistant", "content": salida})
        # Hacer que el navegador lea la respuesta en voz alta
        hablar_en_navegador(salida)
        st.rerun()


def componente_voz():
    """Botón que usa Web Speech (reconocimiento) y escribe el resultado en el input de Streamlit."""
    html = """
    <div style="text-align:center; margin-bottom:8px">
      <button id="btnHablar" style="background:#2aa6b8;color:#fff;border:none;
        border-radius:24px;padding:12px 26px;font-size:1rem;font-weight:600;cursor:pointer">
        🎙️ Hablar
      </button>
      <div id="estado" style="font-size:.85rem;color:#6b7681;margin-top:6px">Listo</div>
    </div>
    <script>
    const btn = document.getElementById('btnHablar');
    const estado = document.getElementById('estado');
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if(!SR){
      estado.textContent = "Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.";
      btn.disabled = true;
    } else {
      const rec = new SR();
      rec.lang = 'es-ES'; rec.interimResults = false; rec.maxAlternatives = 1;
      btn.onclick = () => { estado.textContent = "Escuchando…"; rec.start(); };
      rec.onresult = (e) => {
        const texto = e.results[0][0].transcript;
        estado.textContent = "Dijiste: " + texto;
        // Buscar el input de texto de Streamlit en la página padre y rellenarlo
        const inputs = window.parent.document.querySelectorAll('input[type="text"]');
        if(inputs.length){
          const campo = inputs[inputs.length-1];
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
          setter.call(campo, texto);
          campo.dispatchEvent(new Event('input', {bubbles:true}));
        }
      };
      rec.onerror = (e) => { estado.textContent = "Error: " + e.error; };
      rec.onend = () => { if(estado.textContent==="Escuchando…") estado.textContent="Listo"; };
    }
    </script>
    """
    components.html(html, height=110)


def hablar_en_navegador(texto):
    """Hace que el navegador lea el texto en voz alta con Web Speech (síntesis)."""
    seguro = texto.replace("\\", "").replace("`", "'").replace('"', "'").replace("\n", " ")
    html = f"""
    <script>
    const u = new SpeechSynthesisUtterance("{seguro}");
    u.lang = 'es-ES'; u.rate = 1; u.pitch = 1;
    const voces = window.speechSynthesis.getVoices().filter(v => v.lang.startsWith('es'));
    if(voces.length) u.voice = voces[0];
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
    </script>
    """
    components.html(html, height=0)


# ============================================================================
# PANTALLA: MAPA (subir imagen → Claude detecta → recompensa)
# ============================================================================
# Lo que Claude debe detectar para premiar. Cámbialo por tu objetivo real.
OBJETIVO_DETECCION = "una palma de cera (la palma alta y delgada típica del Valle de Cocora, Quindío)"

SYSTEM_VISION = f"""Eres el validador de misiones de una app de turismo en Colombia.
El jugador debe encontrar y fotografiar este objetivo: {OBJETIVO_DETECCION}.

Analiza la imagen y responde ÚNICAMENTE en este formato exacto:
DETECTADO: SI    (si el objetivo aparece claramente)
o
DETECTADO: NO    (si no aparece)
Luego, en una línea aparte, una frase corta (máx 20 palabras) explicando qué ves."""


def pantalla_mapa():
    st.markdown('<div class="titulo-grande">🗺️ Mapa explorador</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">Encuentra el objetivo de la misión y captúralo</div>', unsafe_allow_html=True)

    st.markdown(f"**🎯 Misión:** encuentra y sube una foto de **{OBJETIVO_DETECCION}**.")
    st.caption("Más adelante aquí irá tu imagen de mapa. Por ahora, sube la foto que Claude debe revisar.")

    cli = cliente()
    if cli is None:
        st.error("Configura tu API key (barra lateral o Secrets) para validar la misión.")
        return

    archivo = st.file_uploader("Sube tu foto", type=["jpg", "jpeg", "png", "webp"])
    if archivo:
        st.image(archivo, caption="Tu captura", use_container_width=True)
        if st.button("🔍 Validar misión"):
            datos = archivo.getvalue()
            b64 = base64.standard_b64encode(datos).decode("utf-8")
            tipo = archivo.type if archivo.type else "image/jpeg"
            with st.spinner("Claude está revisando tu imagen…"):
                try:
                    resp = cli.messages.create(
                        model=MODELO, max_tokens=200, system=SYSTEM_VISION,
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
                st.session_state.recompensa_dada = True
                st.balloons()
                st.markdown(
                    f'<div class="premio">🏆 <b>¡Misión cumplida!</b><br>{comentario}'
                    f'<br><br>Recompensa: <b>+100 puntos Raíces</b> 🌿<br>'
                    'Insignia desbloqueada: <b>Explorador del Cocora</b></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.warning(f"Aún no detecto el objetivo. {comentario}")
                st.caption("Inténtalo con otra foto donde el objetivo se vea claro.")


# ============================================================================
# PANTALLA: AR (no disponible)
# ============================================================================
def pantalla_ar():
    st.markdown('<div class="titulo-grande">🥽 Realidad Aumentada</div>', unsafe_allow_html=True)
    st.info("🚧 **No disponible** — esta etapa llegará en una próxima versión del proyecto.")


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
elif P == "mapa":
    pantalla_mapa()
elif P == "ar":
    pantalla_ar()
