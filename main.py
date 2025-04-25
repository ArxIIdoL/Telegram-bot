import fitz
import io
import os
import tempfile
import convertapi
from telegram import Update, InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from config import BOT_TOKEN, CONVERTAPI_SECRET

convertapi.api_credentials = CONVERTAPI_SECRET


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Привет! 👋 Я многофункциональный бот!', reply_markup=ReplyKeyboardRemove())


##################################################Функции для PDF Merger################################################
pdf_files = []


def merge_pdfs(pdf_files: list[bytes]):
    merged_doc = fitz.open()
    for pdf_file in pdf_files:
        try:
            pdf_document = fitz.open(stream=pdf_file, filetype="pdf")
            merged_doc.insert_pdf(pdf_document)
        except Exception as e:
            print(f"Ошибка при обработке PDF: {e}")
            continue
    merged_pdf_bytes = merged_doc.tobytes()
    merged_doc.close()
    return merged_pdf_bytes


async def pdf_merger_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Объединить"],
        ["Инструкция"],
        ["Выйти"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите действие:",
                                   reply_markup=reply_markup)
    pdf_files.clear()
    context.user_data['state'] = 'pdf_merger_menu'


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Объединить"],
        ["Инструкция"],
        ["Выйти"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    text = update.message.text

    if context.user_data.get('state') == 'waiting_for_pdfs' and text == "Готово!":
        await merge(update, context)
        return

    if text == "Объединить" and context.user_data['state'] == 'pdf_merger_menu':
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Отправьте мне несколько PDF-файлов, и я объединю их в один. Когда закончите, нажмите 'Готово!'",
                                       reply_markup=ReplyKeyboardRemove())
        pdf_files.clear()
        context.user_data['state'] = 'waiting_for_pdfs'
    elif text == "Инструкция" and context.user_data['state'] == 'pdf_merger_menu':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Здесь будет инструкция...",
                                       reply_markup=reply_markup)
    elif text == "Выйти" and context.user_data['state'] == 'pdf_merger_menu':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы вышли в главное меню",
                                       reply_markup=ReplyKeyboardRemove())
        context.user_data['state'] = 'menu'
    elif context.user_data.get('state') == 'format_converter_waiting' and text == "Выйти":
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы вышли в главное меню",
                                       reply_markup=ReplyKeyboardRemove())
        context.user_data['state'] = 'menu'


async def pdf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pdf_files
    file_id = update.message.document.file_id
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()
    pdf_files.append(bytes(file_bytes))

    keyboard = [["Готово!"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Файл получен. ✅", reply_markup=reply_markup)


async def merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global pdf_files
    if not pdf_files:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Нет файлов для объединения. 😔 Отправьте сначала PDF-файлы.",
                                       reply_markup=ReplyKeyboardRemove())
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Объединяю файлы... ⏳",
                                   reply_markup=ReplyKeyboardRemove())
    try:
        merged_pdf = merge_pdfs(pdf_files)
        if merged_pdf:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=InputFile(io.BytesIO(merged_pdf), filename="merged_document.pdf"),
                caption="Ваш объединенный PDF-файл! 📁"
            )
            pdf_files.clear()
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text="Произошла ошибка при объединении файлов. ❌",
                                           reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Произошла ошибка: {e} 😢",
                                       reply_markup=ReplyKeyboardRemove())
    finally:
        pdf_files.clear()
        context.user_data['state'] = 'menu'


##########################################Функции для Format Converter##################################################
async def format_converter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['Выйти']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text('Отправьте мне фотографию, и я сконвертирую ее в PNG. 📸', reply_markup=reply_markup)
    context.user_data['state'] = 'format_converter_waiting'


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') != 'format_converter_waiting':
        await context.bot.send_message(chat_id=update.effective_chat.id, text='Произошла ошибка')
        return

    temp_file_path = None
    converted_file_path = None

    try:
        file_id = update.message.photo[-1].file_id
        file_info = await context.bot.get_file(file_id)
        downloaded_file = await file_info.download_as_bytearray()
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(downloaded_file)
            temp_file_path = temp_file.name
        converted_file = convertapi.convert(
            'png', {'File': temp_file_path}
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as converted_temp_file:
            converted_file_path = converted_temp_file.name
            converted_file.save_files(converted_file_path)
        with open(converted_file_path, 'rb') as f:
            await context.bot.send_document(chat_id=update.effective_chat.id,
                                            document=InputFile(f, filename="converted_image.png"))

    except Exception as e:
        await update.message.reply_text(f'Произошла ошибка при конвертации: {e} 😥')
    finally:
        if temp_file_path:
            try:
                os.remove(temp_file_path)
            except Exception as e:
                await update.message.reply_text(f"Ошибка при удалении временного файла: {e}")
        if converted_file_path:
            try:
                os.remove(converted_file_path)
            except Exception as e:
                await update.message.reply_text(f"Ошибка при удалении сконвертированного файла: {e}")


if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Добавляем обработчик команды start
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    # Handlers для PDF Merger
    pdf_merger_start_handler = CommandHandler('pdf_merger', pdf_merger_start)
    application.add_handler(pdf_merger_start_handler)
    handle_text = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    application.add_handler(handle_text)
    pdf_handler_instance = MessageHandler(filters.Document.MimeType("application/pdf"), pdf_handler)
    application.add_handler(pdf_handler_instance)

    # Handlers для Format Converter
    format_converter_start_handler = CommandHandler('format_converter', format_converter_start)
    application.add_handler(format_converter_start_handler)
    photo_handler = MessageHandler(filters.PHOTO, photo)
    application.add_handler(photo_handler)

    application.run_polling()
