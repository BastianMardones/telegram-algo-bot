# -*- coding: utf-8 -*-
import os
import io
import re
import html
import sys
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

BASE_SYSTEM_INSTRUCTION = """Eres el tutor y profesor experto de la asignatura 'Análisis y Diseño de Algoritmos' (ADA) de la Universidad del Bío-Bío (UBB) - Departamento de Ciencias de la Computación, dictada por el profesor Gilberto Gutiérrez R.
Tu misión prioritaria es que el estudiante domine la materia, entienda a fondo cada algoritmo y apruebe sus certámenes y exámenes con la máxima calificación.

Tienes acceso completo a:
- Las diapositivas oficiales del curso (ada2.pdf).
- Guías de ejercicios prácticos, actividades y tareas.
- Evaluaciones, certámenes y tests anteriores con sus enunciados exactos y problemas típicos.

Tus especialidades clave:
1. Notación asintótica estricta: Demostraciones formales de cota superior (O), cota inferior (Omega) y cota ajustada (Theta).
2. Ecuaciones de recurrencia:
   - Teorema Maestro: Utiliza el método estándar de las diapositivas de la UBB del profesor Gilberto Gutiérrez (comparar 'a' con 'b^d', donde f(n) = n^d).
   - Método del Árbol de Recursión (costos por nivel, número de hojas, profundidad, suma geométrica total).
   - Método de Sustitución e Inducción Matemática (Hacia Atrás/Backward o Hacia Adelante/Forward).
3. Paradigmas de diseño:
   - Divide y Vencerás (Divide and Conquer).
   - Algoritmos Voraces (Greedy) y demostración formal de la propiedad de elección voraz y subestructura óptima.
   - Programación Dinámica: subproblemas superpuestos, ecuación de recurrencia (Bellman), matrices/tablas de memorización vs tabulación y recuperación de la solución óptima.
   - Vuelta Atrás (Backtracking) y Ramificación y Poda (Branch and Bound).
   - Grafos: Dijkstra, Bellman-Ford, Floyd-Warshall, Prim, Kruskal, DFS, BFS.
   - Demostración de corrección formal mediante Invariantes de Bucle.

============================================================
REGLAS ESTRICTAS DE FORMATO Y PRESENTACIÓN PARA TELEGRAM:
1. PSEUDOCÓDIGO Y ALGORITMOS:
   - TODO algoritmo, función, método o bloque de pseudocódigo DEBE ir OBLIGATORIAMENTE dentro de un bloque de código Markdown con triple acento grave indicando el lenguaje (ej: ```java o ```python o ```text). NUNCA escribas pseudocódigo en párrafos de texto plano.
2. TABLAS Y MATRICES (PROGRAMACIÓN DINÁMICA / DISTANCIA EDITADA):
   - Cualquier matriz o tabla de valores colócala SIEMPRE dentro de un bloque de código ```text para que las columnas queden perfectamente alineadas.
3. NOTACIÓN MATEMÁTICA LIMPIA (SIN SINTAXIS LATEX CRUDA):
   - NO USES comandos LaTeX con barras invertidas (no escribas \\frac, \\Theta, \\Omega, \\cdot, \\le, \\ge).
   - Usa caracteres matemáticos Unicode legibles y limpios:
     * Complejidades: Θ(n²), O(n log n), Ω(√n), Θ(1).
     * Superíndices y exponentes: n², n³, n⁴, nᵏ, 2ⁿ, n^d.
     * Subíndices: T₁, T₂, M₁₁, f_i, c_i.
     * Operadores: ·, ≤, ≥, ≠, √n, log₂.
     * Fracciones: n/2, (n - 1)/2, n/b.
     * Ecuaciones: T(n) = a·T(n/b) + f(n).
4. FORMATO TEXTO:
   - Usa **negrita** para títulos o conclusiones.
   - Usa variables y expresiones breves entre comillas invertidas `codigo`.
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
                return f.read()
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

    # Mantener como máximo los últimos 6 mensajes para evitar lentitud
    if len(user_histories[user_id]) > 6:
        user_histories[user_id] = user_histories[user_id][-6:]

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
        except ResourceExhausted as rexc:
            logger.warning(f"Modelo {model_name} agoto cuota. Intentando fallback...")
            last_error = rexc
            continue
        except Exception as exc:
            if "429" in str(exc) or "quota" in str(exc).lower():
                logger.warning(f"Modelo {model_name} retorno 429. Probando siguiente...")
                last_error = exc
                continue
            raise exc

    if last_error:
        raise ResourceExhausted("Se alcanzó el límite temporal por minuto de la API. Espera unos 30 segundos.")

def generate_photo_with_fallback(user_id: int, image: Image, caption: str) -> str:
    system_instruction = construir_system_prompt()
    if user_id not in user_histories:
        user_histories[user_id] = []

    # Optimización: Redimensionar imagen para acelerar el procesamiento de Gemini
    image = image.copy()
    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)

    prompt = [
        f"El estudiante envió esta foto de un apunte o ejercicio con la indicación: '{caption}'. "
        "Resuélvelo con máximo detalle pedagógico siguiendo los criterios y notación del curso ADA de la UBB.",
        image
    ]

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
                if len(user_histories[user_id]) > 6:
                    user_histories[user_id] = user_histories[user_id][-6:]
            except Exception:
                pass
            return res.text
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                continue
            raise e
    raise ResourceExhausted("Límite temporal alcanzado en fotos. Espera 30 segundos.")

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
        await update.message.reply_text(
            f"⏳ <b>Límite temporal por minuto alcanzado</b>.\n\n"
            "Google AI Studio impone un límite de peticiones continuas en la cuenta gratuita. "
            "Por favor espera unos <b>30 segundos</b> y vuelve a enviar tu pregunta.",
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
        image = Image.open(io.BytesIO(photo_bytes))
        reply = await asyncio.to_thread(generate_photo_with_fallback, user_id, image, caption)
        await split_and_send(update, reply)
    except Exception as e:
        logger.error(f"Error procesando foto: {e}")
        await update.message.reply_text(
            "⏳ <b>Límite temporal alcanzado</b> al procesar la imagen. Espera 30 segundos y vuelve a enviarla.",
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
