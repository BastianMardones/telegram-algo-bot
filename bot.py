# -*- coding: utf-8 -*-
import os
import io
import re
import sys
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
from pypdf import PdfReader
import google.generativeai as genai
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Compatibilidad con Render Web Service (Free Tier $0)
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
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

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
   - Teorema Maestro (indicando condiciones, comparación entre n^(log_b(a)) y f(n), y los 3 casos formales).
   - Método del Árbol de Recursión (costos por nivel, profundidad, suma total).
   - Método de Sustitución e Inducción Matemática (Hacia Atrás/Backward o Hacia Adelante/Forward).
3. Paradigmas de diseño:
   - Divide y Vencerás (Divide and Conquer).
   - Algoritmos Voraces (Greedy) y demostración formal de la propiedad de elección voraz y subestructura óptima.
   - Programación Dinámica: subproblemas superpuestos, ecuación de recurrencia (Bellman), matrices/tablas de memorización vs tabulación y recuperación de la solución óptima.
   - Vuelta Atrás (Backtracking) y Ramificación y Poda (Branch and Bound).
   - Grafos: Dijkstra, Bellman-Ford, Floyd-Warshall, Prim, Kruskal, DFS, BFS.
   - Demostración de corrección formal mediante Invariantes de Bucle.

============================================================
REGLAS OBLIGATORIAS DE FORMATO PARA TELEGRAM (¡MUY IMPORTANTE!):
Telegram NO soporta LaTeX ni encabezados '#' de Markdown. Si usas LaTeX o '#', el texto se ve feo y roto.

Sigue estas reglas al redactar tus respuestas:
1. NUNCA uses símbolos de LaTeX como $$, $, \\big, \\frac, \\sum, \\cdot, \\theta, \\in.
2. Escribe las fórmulas matemáticas con caracteres claros o bloques de código monoespaciado.
   - En vez de: $$f(n) = 2f(n-1) + 1$$, escribe:
     `f(n) = 2·f(n-1) + 1` o simplemente f(n) = 2·f(n-1) + 1
   - Para potencias usa superíndices reales Unicode (², ³, ⁿ, ᵏ) o el circunflejo: 2ⁿ, 2^k, n².
   - Para complejidades usa: O(n log n), Θ(n²), Ω(2ⁿ).
3. NUNCA uses encabezados tipo '###' o '####' porque Telegram los muestra como texto plano con numerales.
   - En su lugar, usa negritas limpias y emojis para estructurar:
     *📌 Método: Sustitución Hacia Atrás (Backward)*
     *Paso 1: Aplicar la sustitución de forma iterativa*
4. Si vas a mostrar una deducción paso a paso o una tabla, colócala dentro de un bloque de código:
```text
Paso 1: f(n) = 2*f(n-1) + 1
Paso 2: f(n) = 2*(2*f(n-2) + 1) + 1 = 4*f(n-2) + 3
Paso 3: f(n) = 8*f(n-3) + 7
Paso k: f(n) = 2^k * f(n-k) + (2^k - 1)
```
Esto garantiza que la respuesta se lea perfectamente limpia y clara en la app de Telegram móvil y desktop.
============================================================
"""

def limpiar_formato_telegram(texto: str) -> str:
    """Limpia automáticamente cualquier residuo de LaTeX o encabezados Markdown que el LLM pudiera generar."""
    texto = re.sub(r'^[#]+\s*(.+)$', r'*\1*', texto, flags=re.MULTILINE)
    texto = texto.replace(r'\big(', '(').replace(r'\big)', ')')
    texto = texto.replace(r'\Big(', '(').replace(r'\Big)', ')')
    texto = texto.replace(r'\cdot', '·').replace(r'\times', '×')
    texto = texto.replace(r'\leq', '≤').replace(r'\geq', '≥').replace(r'\neq', '≠')
    texto = texto.replace(r'\Theta', 'Θ').replace(r'\Omega', 'Ω')
    texto = texto.replace(r'\sum', 'Σ')
    
    # Convertir $$formula$$ en bloques de código o texto limpio
    def replace_double_dollar(match):
        expr = match.group(1).strip()
        return f"\n```\n{expr}\n```\n"
    texto = re.sub(r'\$\$(.*?)\$\$', replace_double_dollar, texto, flags=re.DOTALL)
    
    # Convertir $formula$ en `formula`
    texto = re.sub(r'\$([^\$\n]+?)\$', r'`\1`', texto)
    return texto

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

user_chats = {}

def get_or_create_chat(user_id: int):
    if user_id not in user_chats:
        system_instruction = construir_system_prompt()
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=system_instruction
        )
        user_chats[user_id] = model.start_chat(history=[])
    return user_chats[user_id]

async def split_and_send(update: Update, text: str):
    text_limpio = limpiar_formato_telegram(text)
    max_len = 4000
    for i in range(0, len(text_limpio), max_len):
        chunk = text_limpio[i:i + max_len]
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text(chunk)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_chats.pop(user_id, None)
    
    welcome_text = (
        "👋 ¡Hola! Soy tu tutor para el curso de *Análisis y Diseño de Algoritmos (ADA)* de la *Universidad del Bío-Bío*.\n\n"
        "📚 *Material de cátedra cargado:*\n"
        "• ✅ Diapositivas oficiales del curso (*ada2.pdf*)\n"
        "• ✅ Certámenes anteriores transcritos (Certamen 1, Certamen 2, Tests)\n"
        "• ✅ Prácticas y tareas oficiales (Programación Dinámica, Divide y Vencerás, etc.)\n\n"
        "💡 *¿Cómo puedo ayudarte a estudiar?*\n"
        "• Envíame cualquier ejercicio de la guía o tus dudas teóricas.\n"
        "• 📷 *¡Fotos!* Mándame fotos de tus apuntes o pizarrones y los analizaré con rigor.\n"
        "• 🎯 `/practicar [tema]` - Te pondré un ejercicio de certamen real para que intentes resolverlo.\n"
        "• 📄 `/certamenes` - Ver problemas tipo certamen de la cátedra.\n"
        "• 🔄 `/nuevo` - Reiniciar conversación para un nuevo tema o ejercicio.\n"
        "• 📎 Puedes seguir enviando PDFs o fotos por aquí y los incorporaré automáticamente."
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_chats.pop(user_id, None)
    await update.message.reply_text("🔄 Conversación reiniciada. ¿Qué ejercicio o tema de ADA quieres estudiar hoy?")

async def certamenes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = get_or_create_chat(user_id)
    prompt = (
        "Menciónale al estudiante qué tipo de problemas típicos entraron en los Certámenes 1 y 2 anteriores del profesor "
        "Gilberto Gutiérrez (por ejemplo mySort, análisis de recursión, Divide y Vencerás o Programación Dinámica) "
        "y pregúntale cuál de ellos quiere que resolvamos o practiquemos juntos."
    )
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        response = chat.send_message(prompt)
        await split_and_send(update, response.text)
    except Exception as e:
        logger.error(f"Error en /certamenes: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def practicar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    topic = " ".join(context.args) if context.args else "Certamen de la UBB"
    chat = get_or_create_chat(user_id)
    
    prompt = (
        f"El estudiante quiere practicar para su examen sobre el tema o certamen: '{topic}'. "
        "Plantea un problema real o adaptado de los certámenes o diapositivas de la UBB. "
        "Explica el enunciado con total claridad y pídele que proponga su estrategia, algoritmo y complejidad. "
        "No des la respuesta todavía, sé socrático."
    )
    
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        response = chat.send_message(prompt)
        await split_and_send(update, response.text)
    except Exception as e:
        logger.error(f"Error en /practicar: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text
    chat = get_or_create_chat(user_id)

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        response = chat.send_message(user_text)
        await split_and_send(update, response.text)
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photos = update.message.photo
    caption = update.message.caption or "Analiza y resuelve este ejercicio paso a paso según los criterios de ADA de la UBB."

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        photo_file = await photos[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))

        system_instruction = construir_system_prompt()
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=system_instruction
        )
        prompt = [
            f"El estudiante envió esta foto de un apunte o ejercicio con la indicación: '{caption}'. "
            "Resuélvelo con máximo detalle pedagógico siguiendo los criterios y notación del curso ADA de la UBB.",
            image
        ]
        
        response = model.generate_content(prompt)
        await split_and_send(update, response.text)
    except Exception as e:
        logger.error(f"Error procesando foto: {e}")
        await update.message.reply_text(f"❌ Error al procesar la imagen: {e}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    filename = doc.file_name
    valid_exts = [".pdf", ".txt", ".md"]
    ext = Path(filename).suffix.lower()
    
    if ext not in valid_exts:
        await update.message.reply_text(f"⚠️ El archivo `{filename}` no es compatible (.pdf, .txt o .md).")
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

        user_chats.clear()
        await update.message.reply_text(
            f"✅ *¡Documento `{filename}` indexado con éxito!*\n"
            "Ya está incorporado en la base de conocimientos del bot para responderte.",
            parse_mode=ParseMode.MARKDOWN
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

    print("[+] Bot ADA iniciado con formateo limpio para Telegram.")
    app.run_polling()

if __name__ == "__main__":
    main()