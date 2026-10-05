# -*- coding: utf-8 -*-
import os
import io
import re
import html
import sys
import time
import logging
import threading
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
from pypdf import PdfReader
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Servidor Web interno para Keep-Alive en Render
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ADA is running successfully!")

    def log_message(self, format, *args):
        pass

def run_health_check_server():
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_health_check_server, daemon=True).start()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "documentos"
CACHE_FILE = BASE_DIR / "documentos_cache.txt"
DOCS_DIR.mkdir(exist_ok=True)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

BASE_SYSTEM_INSTRUCTION = """Eres el tutor experto de 'Análisis y Diseño de Algoritmos' (ADA) de la Universidad del Bío-Bío (UBB) - Departamento de Ciencias de la Computación, cátedra del profesor Gilberto Gutiérrez R.
Tu objetivo es que el estudiante domine la materia con máximo rigor y resuelva sus certámenes con la máxima calificación (nota 7.0).

Tienes acceso completo a:
- Diapositivas oficiales del curso (ada2.pdf).
- Guías de ejercicios prácticos, actividades y tareas.
- Evaluaciones, certámenes y tests anteriores con sus enunciados exactos y criterios de corrección.

============================================================
CRITERIOS PEDAGÓGICOS Y RIGOR TEÓRICO DE CÁTEDRA (UBB):
1. ESTRUCTURA CANÓNICA DE DIVIDIR PARA REINAR (ESTILO MERGESORT):
   - Fase de División: Describir formalmente la partición en subproblemas de tamaño n/b (sin operaciones de mezcla previas).
   - Fase de Conquista: Realizar SIEMPRE primero las llamadas recursivas sobre los subproblemas.
   - Fase de Combinación: Todo trabajo de fusión, pegado o intercambio de bloques (swap) DEBE ejecutarse obligatoriamente DESPUÉS de las llamadas recursivas. NUNCA llames 'Combinación' a pasos previos a la recursión.
   - Terminología: Usar términos precisos como 'bloques fuera de la diagonal principal' (M12 y M21).
2. ECUACIONES DE RECURRENCIA Y CASOS BASE:
   - Mantén estricta coherencia entre el caso base y el rango de validez.
   - Si el caso base es n = 1 con 0 operaciones: T(n) = a·T(n/b) + f(n) para n > 1, con T(1) = 0.
   - Si el caso base es n = 2 con 1 operación: T(n) = a·T(n/b) + f(n) para n > 2, con T(2) = 1.
3. PROGRAMACIÓN DINÁMICA Y TRAZABILIDAD (DISTANCIA DE EDICIÓN / MOCHILA):
   - Además de construir la matriz de tabulación con las dimensiones y valores exactos, al explicar la reconstrucción de la solución óptima (backtracking), verifica la cadena intermedia paso a paso: ej: u -> u' -> v con sus costos unitarios.
============================================================

REGLAS DE FORMATO Y PRESENTACIÓN (OPTIMIZADO PARA SMARTWATCH Y MÓVIL):
1. CERO SALUDOS NI INTRODUCCIONES LARGAS:
   - Ve directo al grano del ejercicio o pregunta.
2. FICHA RÁPIDA INICIAL:
   - Al inicio de cada problema, coloca en 3 líneas:
     * 📌 Recurrencia / Ecuación
     * ⚖️ Teorema Maestro / Técnica usada
     * 🎯 Complejidad final
3. PSEUDOCÓDIGO LIMPIO Y SIN COMENTARIOS:
   - TODO pseudocódigo DEBE ir dentro de ```java o ```text.
   - NUNCA pongas comentarios (// ...) dentro del código.
   - Ancho máximo de línea: 25 a 30 caracteres (dividir parámetros verticalmente).
   - Sangría de 2 espacios.
4. ÁRBOLES DE RECURSIÓN VERTICALES:
   - SIEMPRE de forma vertical con caracteres de lista (├─, └─, │) o agrupados por niveles. Nunca diagonales (/ \\).
5. NOTACIÓN MATEMÁTICA CON UNICODE:
   - Usa siempre símbolos Unicode limpios: Θ(n²), O(n log n), Ω(√n), n², T(n) = a·T(n/b) + f(n), log₂.
============================================================
"""

def limpiar_latex_a_unicode(texto: str) -> str:
    """Convierte comandos típicos de LaTeX a símbolos Unicode limpios para Telegram."""
    reemplazos = [
        (r'\\Theta', 'Θ'),
        (r'\\Omega', 'Ω'),
        (r'\\mathcal\{O\}', 'O'),
        (r'\\le(?:q)?', '≤'),
        (r'\\ge(?:q)?', '≥'),
        (r'\\neq', '≠'),
        (r'\\cdot', '·'),
        (r'\\times', '×'),
        (r'\\approx', '≈'),
        (r'\\infty', '∞'),
        (r'\\dots', '...'),
        (r'\\log_2', 'log₂'),
        (r'\\log_b', 'log_b'),
        (r'\\sqrt\{([^}]+)\}', r'√(\1)'),
        (r'\\frac\{([^}]+)\}\{([^}]+)\}', r'(\1)/(\2)'),
        (r'\\left\(', '('),
        (r'\\right\)', ')'),
        (r'\\left\[', '['),
        (r'\\right\]', ']'),
        (r'\\text\{([^}]+)\}', r'\1'),
    ]
    for patron, rep in reemplazos:
        texto = re.sub(patron, rep, texto)
    return texto

def formatear_para_telegram(texto: str) -> str:
    texto = limpiar_latex_a_unicode(texto)

    # 1. Proteger tablas Markdown para que se vean alineadas en un bloque monoespaciado
    def guardar_tabla(m):
        contenido = html.escape(m.group(0).strip())
        return f"\n<pre>{contenido}</pre>\n"
    texto = re.sub(r'(\|[^\n]+\|\n\|[-:| ]+\|\n(?:\|[^\n]+\|\n?)+)', guardar_tabla, texto)

    # 2. Proteger bloques de código ```
    bloques = []
    def guardar_bloque(m):
        lang = m.group(1) or ""
        contenido = html.escape(m.group(2).strip())
        if lang:
            bloques.append(f'<pre><code class="language-{lang}">{contenido}</code></pre>')
        else:
            bloques.append(f'<pre>{contenido}</pre>')
        return f"___BLOQUE_{len(bloques)-1}___"

    texto = re.sub(r'```([a-zA-Z0-9_-]+)?\n?(.*?)```', guardar_bloque, texto, flags=re.DOTALL)

    # 3. Proteger inlines `codigo` y formulas $...$
    inlines = []
    def guardar_inline(m):
        c = html.escape(m.group(1).strip())
        inlines.append(f"<code>{c}</code>")
        return f"___INLINE_{len(inlines)-1}___"

    texto = re.sub(r'`([^`\n]+)`', guardar_inline, texto)
    texto = re.sub(r'\$\$(.*?)\$\$', guardar_inline, texto, flags=re.DOTALL)
    texto = re.sub(r'\$([^\$\n]+?)\$', guardar_inline, texto)

    # 4. Escapar texto plano
    texto = html.escape(texto)

    # 5. Formatear títulos y negritas
    texto = re.sub(r'^[#]+\s*(.+)$', r'<b>\1</b>', texto, flags=re.MULTILINE)
    texto = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', texto)
    # Cursivas solo para palabras aisladas (evita romper variables con guion bajo como f_i o c_i)
    texto = re.sub(r'(?<!\w)_([^_]+?)_(?!\w)', r'<i>\1</i>', texto)

    # 6. Restaurar bloques protegidos
    for i, cod in enumerate(inlines):
        texto = texto.replace(f"___INLINE_{i}___", cod)
    for i, blk in enumerate(bloques):
        texto = texto.replace(f"___BLOQUE_{i}___", blk)

    return texto

def dividir_en_chunks_markdown(text: str, max_len: int = 3500) -> list:
    """Divide un texto Markdown largo en fragmentos que respetan bloques de código."""
    if len(text) <= max_len:
        return [text]

    lineas = text.split("\n")
    chunks = []
    chunk_actual = []
    longitud_actual = 0
    en_bloque_codigo = False
    lenguaje_codigo = ""

    for linea in lineas:
        if linea.strip().startswith("```"):
            if not en_bloque_codigo:
                en_bloque_codigo = True
                lenguaje_codigo = linea.strip().replace("```", "")
            else:
                en_bloque_codigo = False
                lenguaje_codigo = ""

        # ¿Se supera el tamaño máximo por mensaje?
        if longitud_actual + len(linea) + 1 > max_len and chunk_actual:
            if en_bloque_codigo:
                # Cerrar limpiamente el bloque en este chunk y reabrirlo en el siguiente
                chunk_actual.append("```")
                chunks.append("\n".join(chunk_actual).strip())
                chunk_actual = [f"```{lenguaje_codigo}", linea]
                longitud_actual = len(chunk_actual[0]) + len(linea) + 1
            else:
                chunks.append("\n".join(chunk_actual).strip())
                chunk_actual = [linea]
                longitud_actual = len(linea)
        else:
            chunk_actual.append(linea)
            longitud_actual += len(linea) + 1

    if chunk_actual:
        if en_bloque_codigo:
            chunk_actual.append("```")
        chunks.append("\n".join(chunk_actual).strip())

    return chunks

def obtener_conocimiento():
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8", errors="ignore") as f:
                # Limitar a máximo 40KB para no saturar los límites de tokens por minuto (TPM)
                return f.read()[:40000]
        except Exception as e:
            logger.error(f"Error leyendo cache: {e}")
    return ""

def construir_system_prompt():
    docs_text = obtener_conocimiento()
    if docs_text:
        return f"{BASE_SYSTEM_INSTRUCTION}\n\n--- MATERIAL OFICIAL DE ESTUDIO, CERTÁMENES Y APUNTES DE LA CÁTEDRA ---\n{docs_text}\n--- FIN DE APUNTES ---"
    return BASE_SYSTEM_INSTRUCTION

user_histories = {}

def send_with_fallback(user_id: int, message_text: str) -> str:
    system_instruction = construir_system_prompt()
    if user_id not in user_histories:
        user_histories[user_id] = []

    # Mantener como máximo los últimos 4 mensajes para optimizar tokens y velocidad
    if len(user_histories[user_id]) > 4:
        user_histories[user_id] = user_histories[user_id][-4:]

    history = user_histories[user_id]
    last_error = None

    for model_name in FALLBACK_MODELS:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction
            )
            chat = model.start_chat(history=history)
            response = chat.send_message(message_text)
            user_histories[user_id] = chat.history
            return response.text
        except Exception as exc:
            logger.warning(f"Modelo {model_name} fallo: {exc}")
            last_error = exc
            if "429" in str(exc) or "quota" in str(exc).lower():
                time.sleep(3)
            continue

    if last_error:
        raise last_error
    raise RuntimeError("No se pudo obtener respuesta de ningún modelo.")

def generate_photo_with_fallback(user_id: int, photo_bytes: bytearray, caption: str) -> str:
    # Para fotos, usar directamente BASE_SYSTEM_INSTRUCTION para un procesamiento ultrarrápido y liviano
    system_instruction = BASE_SYSTEM_INSTRUCTION
    if user_id not in user_histories:
        user_histories[user_id] = []

    # Cargar y asegurar formato RGB para compatibilidad total con Gemini
    image = Image.open(io.BytesIO(photo_bytes))
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((1024, 1024))

    prompt = [
        f"El estudiante envió esta foto de un apunte o ejercicio con la indicación: '{caption}'. "
        "Resuélvelo con máximo rigor pedagógico siguiendo estrictamente los criterios de la cátedra de ADA de la UBB.",
        image
    ]

    last_error = None
    for model_name in FALLBACK_MODELS:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=system_instruction
            )
            res = model.generate_content(prompt)
            try:
                user_histories[user_id].append({"role": "user", "parts": [f"[Foto de ejercicio enviada]: {caption}"]})
                user_histories[user_id].append({"role": "model", "parts": [res.text]})
                if len(user_histories[user_id]) > 4:
                    user_histories[user_id] = user_histories[user_id][-4:]
            except Exception:
                pass
            return res.text
        except Exception as e:
            logger.warning(f"Modelo {model_name} fallo en foto: {e}")
            last_error = e
            if "429" in str(e) or "quota" in str(e).lower():
                time.sleep(3)
            continue

    if last_error:
        raise last_error
    raise RuntimeError("Error al procesar la foto con los modelos disponibles.")

async def split_and_send(update: Update, text: str):
    # Dividir primero a nivel Markdown para que ningún bloque quede abierto entre mensajes
    chunks = dividir_en_chunks_markdown(text, max_len=3500)

    for chunk in chunks:
        # Formatear cada fragmento como HTML completo e independiente
        chunk_html = formatear_para_telegram(chunk)
        try:
            await update.message.reply_text(chunk_html, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"Error enviando HTML ({e}), enviando en texto plano limpio.")
            # Fallback seguro: limpia etiquetas y decodifica entidades (&gt; -> >, &quot; -> ")
            texto_plano = html.unescape(re.sub(r'<[^>]+>', '', chunk_html))
            await update.message.reply_text(texto_plano)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_histories.pop(user_id, None)
    
    welcome_text = (
        "👋 ¡Hola! Soy tu tutor para el curso de <b>Análisis y Diseño de Algoritmos (ADA)</b> de la <b>Universidad del Bío-Bío</b>.\n\n"
        "📚 <b>Material de cátedra cargado:</b>\n"
        "• ✅ Diapositivas oficiales del curso (<code>ada2.pdf</code>)\n"
        "• ✅ Certámenes anteriores transcritos (Certamen 1, Certamen 2, Tests)\n"
        "• ✅ Prácticas y tareas oficiales (Programación Dinámica, Divide y Vencerás, etc.)\n\n"
        "💡 <b>¿Cómo puedo ayudarte a estudiar?</b>\n"
        "• Envíame cualquier ejercicio de la guía o tus dudas teóricas.\n"
        "• 📷 <b>¡Fotos!</b> Mándame fotos de tus apuntes o pizarrones y los analizaré con rigor.\n"
        "• 🎯 <code>/practicar [tema]</code> - Te pondré un ejercicio de certamen real para que intentes resolverlo.\n"
        "• 📄 <code>/certamenes</code> - Ver problemas tipo certamen de la cátedra.\n"
        "• 🔄 <code>/nuevo</code> - Reiniciar conversación para un nuevo tema o ejercicio.\n"
        "• 📎 Puedes seguir enviando PDFs o fotos por aquí y los incorporaré automáticamente."
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

async def nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_histories.pop(user_id, None)
    await update.message.reply_text("🔄 Memoria reiniciada. ¿Qué nuevo ejercicio o tema quieres ver?")

async def certamenes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prompt = (
        "Menciónale al estudiante qué tipo de problemas típicos entraron en los Certámenes 1 y 2 anteriores del profesor "
        "Gilberto Gutiérrez (por ejemplo mySort, análisis de recursión, Divide y Vencerás o Programación Dinámica) "
        "y pregúntale cuál de ellos quiere que resolvamos o practiquemos juntos."
    )
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        reply = await asyncio.to_thread(send_with_fallback, user_id, prompt)
        await split_and_send(update, reply)
    except Exception as e:
        logger.error(f"Error en /certamenes: {e}")
        await update.message.reply_text(f"⏳ {e}")

async def practicar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    topic = " ".join(context.args) if context.args else "Certamen de la UBB"
    prompt = (
        f"El estudiante quiere practicar para su examen sobre el tema o certamen: '{topic}'. "
        "Plantea un problema real o adaptado de los certámenes o diapositivas de la UBB. "
        "Explica el enunciado con total claridad y pídele que proponga su estrategia, algoritmo y complejidad. "
        "No des la respuesta todavía, sé socrático."
    )
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        reply = await asyncio.to_thread(send_with_fallback, user_id, prompt)
        await split_and_send(update, reply)
    except Exception as e:
        logger.error(f"Error en /practicar: {e}")
        await update.message.reply_text(f"⏳ {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        reply = await asyncio.to_thread(send_with_fallback, user_id, user_text)
        await split_and_send(update, reply)
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        err_str = str(e)
        if "429" in err_str or "quota" in err_str.lower():
            await update.message.reply_text(
                "⏳ <b>Límite temporal por minuto alcanzado</b>.\n\n"
                "Google AI Studio impone un límite en la cuenta gratuita. Por favor espera 30 segundos y vuelve a enviar.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"❌ <b>Error al procesar:</b>\n<code>{html.escape(err_str[:300])}</code>",
                parse_mode=ParseMode.HTML
            )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photos = update.message.photo
    caption = update.message.caption or "Analiza y resuelve este ejercicio paso a paso según los criterios de ADA de la UBB."

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        photo_file = await photos[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        reply = await asyncio.to_thread(generate_photo_with_fallback, user_id, photo_bytes, caption)
        await split_and_send(update, reply)
    except Exception as e:
        logger.error(f"Error procesando foto: {e}", exc_info=True)
        err_str = str(e)
        if "429" in err_str or "quota" in err_str.lower():
            await update.message.reply_text(
                "⏳ <b>Límite temporal alcanzado en fotos</b>.\n\nEspera unos 30 segundos y vuelve a enviarla.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f"❌ <b>Detalle del error en foto:</b>\n<code>{html.escape(err_str[:300])}</code>",
                parse_mode=ParseMode.HTML
            )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    filename = doc.file_name
    valid_exts = [".pdf", ".txt", ".md"]
    ext = Path(filename).suffix.lower()
    
    if ext not in valid_exts:
        await update.message.reply_text(f"⚠️ El archivo <code>{filename}</code> no es compatible (.pdf, .txt o .md).", parse_mode=ParseMode.HTML)
        return

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        dest_path = DOCS_DIR / filename
        doc_file = await doc.get_file()
        await doc_file.download_to_drive(dest_path)
        
        contenido_extra = ""
        if ext == ".pdf":
            r = PdfReader(str(dest_path))
            contenido_extra = "\n".join([p.extract_text() or "" for p in r.pages])
        else:
            with open(dest_path, "r", encoding="utf-8", errors="ignore") as fp:
                contenido_extra = fp.read()
                
        if contenido_extra.strip():
            with open(CACHE_FILE, "a", encoding="utf-8") as c:
                c.write(f"\n=== DOCUMENTO EXTRA: {filename} ===\n{contenido_extra}\n")

        user_histories.clear()
        await update.message.reply_text(
            f"✅ <b>¡Documento <code>{filename}</code> indexado con éxito!</b>\n"
            "Ya está incorporado en la base de conocimientos del bot para responderte.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error guardando documento: {e}")
        await update.message.reply_text(f"❌ Error al procesar el archivo: {e}")

def main():
    if not TELEGRAM_BOT_TOKEN or not GEMINI_API_KEY:
        print("[ERROR] Faltan claves en .env")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", start))
    app.add_handler(CommandHandler("nuevo", nuevo))
    app.add_handler(CommandHandler("certamenes", certamenes))
    app.add_handler(CommandHandler("practicar", practicar))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("[+] Bot ADA iniciado con optimización de formato y rendimiento.")
    app.run_polling()

if __name__ == "__main__":
    main()
