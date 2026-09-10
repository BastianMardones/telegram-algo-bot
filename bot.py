# -*- coding: utf-8 -*-
import os
import io
import sys
import logging
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
   - Método de Sustitución e Inducción Matemática.
3. Paradigmas de diseño:
   - Divide y Vencerás (Divide and Conquer).
   - Algoritmos Voraces (Greedy) y demostración de la propiedad de elección voraz y subestructura óptima.
   - Programación Dinámica: subproblemas superpuestos, ecuación de recurrencia (Bellman), matrices/tablas de memorización vs tabulación y recuperación de la solución óptima.
   - Vuelta Atrás (Backtracking) y Ramificación y Poda (Branch and Bound).
   - Grafos: Dijkstra, Bellman-Ford, Floyd-Warshall, Prim, Kruskal, DFS, BFS.
   - Demostración de corrección formal mediante Invariantes de Bucle (Inicialización, Mantenimiento, Terminación).

Pautas de respuesta:
- Prioriza SIEMPRE la notación, sintaxis de algoritmos y criterios formales de la cátedra de la UBB del profesor Gilberto Gutiérrez.
- Cuando resuelvas un ejercicio, sé pedagógico y exhaustivo:
  1) Intuición y explicación conceptual del problema.
  2) Pseudocódigo claro, estructurado y comentado.
  3) Demostración del análisis de complejidad temporal y espacial paso a paso.
- Cuando el estudiante use /practicar o pida certámenes, utiliza los problemas de los certámenes reales para desafiarlo.
"""

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
    max_len = 4000
    for i in range(0, len(text), max_len):
        chunk = text[i:i + max_len]
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
        "• 📷 **¡Fotos!** Mándame fotos de tus apuntes o pizarrones y los analizaré con rigor.\n"
        "• 🎯 /practicar [tema] - Te pondré un ejercicio de certamen real para que intentes resolverlo.\n"
        "• 📄 /certamenes - Ver problemas tipo certamen de la cátedra.\n"
        "• 🔄 /nuevo - Reiniciar conversación para un nuevo tema o ejercicio.\n"
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
        await update.message.reply_text(f"⚠️ El archivo {filename} no es compatible (.pdf, .txt o .md).")
        return

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        dest_path = DOCS_DIR / filename
        doc_file = await doc.get_file()
        await doc_file.download_to_drive(dest_path)
        
        # Actualizar cache agregando el nuevo archivo
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
            f"✅ *¡Documento {filename} indexado con éxito!*\n"
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

    print("[+] Bot ADA con material oficial de UBB iniciado correctamente.")
    app.run_polling()

if __name__ == "__main__":
    main()