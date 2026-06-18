# 🌿 Raíces de Paz IA — App de demostración

App en Streamlit con cuatro experiencias: Chatbot, Robot guía por voz, Mapa con detección de imagen, y AR (próximamente).

## Archivos
- `app.py` — la aplicación completa
- `requirements.txt` — dependencias

---

## Opción A — Subir a Streamlit Community Cloud (recomendado para la demo)

1. Crea una cuenta gratis en https://share.streamlit.io (con tu cuenta de GitHub).
2. Sube `app.py` y `requirements.txt` a un repositorio de GitHub (público o privado).
3. En Streamlit Cloud: **New app** → elige tu repo → archivo principal: `app.py` → **Deploy**.
4. Cuando cargue, ve al menú **⋮ → Settings → Secrets** y pega:

   ```
   ANTHROPIC_API_KEY = "tu-api-key-aqui"
   ```

5. Guarda. La app se reinicia sola y queda lista con la key segura (nadie la ve).

La URL pública que te da Streamlit es la que muestras el día del evento.

---

## Opción B — Correr en tu computador

```bash
pip install -r requirements.txt
streamlit run app.py
```

Se abre en `http://localhost:8501`. Como no hay Secrets, pega tu API key en la
barra lateral izquierda (campo "API key de Claude").

> ⚠️ La voz del robot necesita **Chrome o Edge** y permiso de micrófono.
> En local a veces el micrófono pide `https`; si falla, usa el campo de texto de respaldo.

---

## Notas para personalizar

- **Objetivo del mapa:** en `app.py`, variable `OBJETIVO_DETECCION` — cambia qué debe
  detectar Claude para dar la recompensa (ahora: una palma de cera del Cocora).
- **Recompensa:** el bloque dentro de `pantalla_mapa()` (puntos, insignia, globos).
- **Modelo:** variable `MODELO` arriba del archivo.
- **Imagen del mapa:** cuando me la envíes, la integramos como fondo de esa pantalla.

---

## Flujo de la app

```
INICIO  →  [ Iniciar ]
   │
   ▼
MENÚ    →  [ Mapa ]   [ Robot ]
           [ Chatbot ][ AR — No disponible ]
```
