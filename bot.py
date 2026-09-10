# -*- coding: utf-8 -*-
import os
import io
import sys
import glob
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

BASE_SYSTEM_INSTRUCTION = """Eres un profesor universitario y tutor experto de la materia 'Análisis y Diseño de Algoritmos'.
Tu objetivo es preparar al estudiante para que apruebe su examen con honores.

Tus especialidades clave:
1. Notación asintótica estricta: O grande, Omega, Theta, demostraciones y propiedades.
2. Ecuaciones de recurrencia: Teorema Maestro (indicando casos y condiciones), Árbol de Recursión, Método de Sustitución e Inducción matemática.
3. Paradigmas de diseño:
   - Divide y Vencerás (Divide and Conquer)
   - Algoritmos Voraces (Greedy) y demostración formal de la propiedad de elección voraz.
   - Programación Dinámica (subestructura óptima, superposición de subproblemas, relación de recurrencia, tabulación vs memoización).
   - Vuelta Atrás (Backtracking) y Ramificación y Poda (Branch and Bound).
   - Algoritmos de Grafos (Dijkstra, Bellman-Ford, Floyd-Warshall, Prim, Kruskal, DFS, BFS).
   - Demostración de corrección mediante Invariantes de Bucle.

Pautas pedagógicas:
- Sé riguroso, claro y estructurado en tus explicaciones.
- Si hay apuntes o bibliografía de la cátedra proporcionados en este prompt, PRIORIZA siempre los criterios, definiciones, notaciones y formatos exigidos por la cátedra.
- En la resolución de ejercicios incluye:
  a) Estrategia general e intuición
  b) Pseudocódigo claro y comentado
  c) Demostración del orden de complejidad temporal y espacial paso a paso.
- Usa notación limpia y legible.
"""

def cargar_documentos():
    textos = []
    archivos = list(DOCS_DIR.glob("*.*"))
    for f in archivos:
        try:
            if f.suffix.lower() == ".pdf":
                reader = PdfReader(str(f))
                contenido = ""
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt:
                        contenido += txt + "\n"
                if contenido.strip():
                    textos.append(f"=== DOCUMENTO DE CÁTEDRA: {f.name} ===\n{contenido}\n")
            elif f.suffix.lower() in [".txt", ".md"]:
                with open(f, "r", encoding="utf-8", errors="ignore") as fp:
                    textos.append(f"=== DOCUMENTO DE CÁTEDRA: {f.name} ===\n{fp.read()}\n")
        except Exception as e:
            logger.error(f"Error leyendo {f.name}: {e}")
    return "\n".join(textos)

def construir_system_prompt():
    docs = cargar_documentos()
    if docs:
        return f"{BASE_SYSTEM_INSTRUCTION}\n\n--- DOCUMENTOS Y APUNTES DE LA CÁTEDRA ---\n{docs}\n--- FIN DE APUNTES ---"
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
    
    docs = list(DOCS_DIR.glob("*.*"))
    docs_info = f"📄 *Documentos cargados:* {len(docs)} archivo(s)" if docs else "📁 *Documentos de cátedra:* Aún no has subido archivos."
    
    welcome_text = (
        "👋 ¡Hola! Soy tu tutor para el examen de *Análisis y Diseño de Algoritmos*.\n\n"
        f"{docs_info}\n\n"
        "📚 *¿Cómo puedo ayudarte?*\n"
        "• Envíame cualquier ejercicio en texto o pseudocódigo que quieras analizar.\n"
        "• 📷 *¡Puedes enviarme una FOTO!* Sácale foto a un examen, guía o pizarrón y la resolveré paso a paso.\n"
        "• 📎 *¡Puedes enviarme PDFs por aquí!* Mándame diapositivas o apuntes como archivo y responderé con los criterios de tu profesor.\n"
        "• Pregúntame sobre Teorema Maestro, recurrencias, complejidad O/Ω/Θ, Programación Dinámica, Grafos, etc.\n\n"
        "🛠 *Comandos útiles:*\n"
        "• /nuevo - Reiniciar la conversación para un nuevo ejercicio.\n"
        "• /practicar [tema] - Ejercicio de examen para que intentes resolverlo tú mismo.\n"
        "• /documentos - Ver la lista de documentos cargados.\n"
        "• /ayuda - Ver este mensaje."
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

async def nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_chats.pop(user_id, None)
    await update.message.reply_text("🔄 Conversación reiniciada. ¿Qué nuevo ejercicio o duda quieres ver?")

async def documentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    docs = list(DOCS_DIR.glob("*.*"))
    if not docs:
        await update.message.reply_text(
            "📁 No hay documentos cargados todavía.\n\n"
            "💡 Puedes enviarme tus archivos PDF o de texto directamente por este chat (como documento adjunto), "
            "o copiarlos en la carpeta 'documentos' de tu computadora."
        )
        return
    lista = "\n".join([f"• 📄 {f.name}" for f in docs])
    await update.message.reply_text(
        f"📚 *Documentos de estudio activos:*\n{lista}\n\n"
        "El bot utiliza estos apuntes para responder con las definiciones y notaciones de tu cátedra.",
        parse_mode=ParseMode.MARKDOWN
    )

async def practicar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    topic = " ".join(context.args) if context.args else "Análisis de recurrencias y complejidad"
    chat = get_or_create_chat(user_id)
    
    prompt = (
        f"Genera un ejercicio típico de examen universitario sobre el tema: '{topic}'. "
        "Plantea solo el problema de forma clara e invita al estudiante a que proponga su idea de solución "
        "y complejidad. No des la solución todavía."
    )
    
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        response = chat.send_message(prompt)
        await split_and_send(update, response.text)
    except Exception as e:
        logger.error(f"Error en /practicar: {e}")
        await update.message.reply_text(f"❌ Error al contactar la API: {e}")

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
    caption = update.message.caption or "Analiza y resuelve este ejercicio paso a paso con rigor pedagógico."

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
            f"El estudiante envió esta imagen de un ejercicio de Algoritmos con la indicación: '{caption}'. "
            "Transcribe el problema si hace falta, resuélvelo paso a paso y demuestra la complejidad temporal y espacial.",
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
        await update.message.reply_text(
            f"⚠️ El archivo {filename} no tiene un formato compatible. Por favor envía archivos .pdf, .txt o .md.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        dest_path = DOCS_DIR / filename
        doc_file = await doc.get_file()
        await doc_file.download_to_drive(dest_path)
        
        user_chats.clear()
        
        await update.message.reply_text(
            f"✅ *¡Documento recibido y guardado!*\n\n"
            f"📄 Archivo: {filename}\n"
            "He actualizado mi base de conocimientos con este nuevo material de estudio. "
            "Las próximas preguntas tomarán en cuenta el contenido de tu cátedra.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Error guardando documento: {e}")
        await update.message.reply_text(f"❌ Error al guardar el archivo: {e}")

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("[ERROR] TELEGRAM_BOT_TOKEN no configurado.")
        return

    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY no configurado.")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", start))
    app.add_handler(CommandHandler("nuevo", nuevo))
    app.add_handler(CommandHandler("documentos", documentos))
    app.add_handler(CommandHandler("practicar", practicar))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("[+] Bot ADA actualizado e iniciado correctamente.")
    app.run_polling()

if __name__ == "__main__":
    main()