import fitz
import io
import os
import tempfile
import convertapi
import csv
import json
import logging
from telegram import Update, InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)
from config import BOT_TOKEN, CONVERTAPI_SECRET

convertapi.api_credentials = CONVERTAPI_SECRET

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

pdf_files = []


async def logging_request(user, request):
    logger.info(f"{user.full_name}(@{user.username}) выполнил запрос '{request}'")


## PDF Merger ##
def merge_pdfs(pdf_files: list[bytes]):
    """Объединяет список байтов PDF-файлов в один"""
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
    """Начало процесса объединения PDF-файлов"""
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
    """Обработка текста от пользователя"""
    text = update.message.text
    if context.user_data.get('state') == 'waiting_for_pdfs' and text == "Готово!":
        await merge(update, context)
        return

    if text == "Объединить" and context.user_data['state'] == 'pdf_merger_menu':
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Отправьте мне несколько PDF-файлов, и я объединю их в один. "
                                            "Когда закончите, нажмите 'Готово!'",
                                       reply_markup=ReplyKeyboardRemove())
        pdf_files.clear()
        context.user_data['state'] = 'waiting_for_pdfs'
    elif text == "Инструкция" and context.user_data['state'] == 'pdf_merger_menu':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Здесь будет инструкция...")
    elif text == "Выйти" and context.user_data['state'] == 'pdf_merger_menu':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы вышли в главное меню",
                                       reply_markup=ReplyKeyboardRemove())
        context.user_data['state'] = 'menu'
    elif context.user_data.get('state') == 'format_converter_waiting' and text == "Выйти":
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Вы вышли в главное меню",
                                       reply_markup=ReplyKeyboardRemove())
        context.user_data['state'] = 'menu'


async def pdf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает полученные PDF-файлы"""
    global pdf_files
    file_id = update.message.document.file_id
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()
    pdf_files.append(bytes(file_bytes))

    keyboard = [["Готово!"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Файл получен. ✅", reply_markup=reply_markup)


async def merge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Объединение полученных PDF-файлов"""
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


## Format Converter ##
async def format_converter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['Выйти']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text('Отправьте мне фотографию, и я сконвертирую ее в другой формат. 📸',
                                    reply_markup=reply_markup)
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


## File Reader / Creator ##
async def reading_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор режима чтения файлов"""
    context.user_data['state'] = 'reading_files'
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Отправьте файл (.txt, .csv, .json), а я пришлю его вам сообщением!")


async def create_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор режима создания файлов"""
    context.user_data['state'] = 'create_files'
    keyboard = [
        ["/create_csv"],
        ["/create_json"],
        ["/create_txt"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите действие:",
                                   reply_markup=reply_markup)


async def reading_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Читает и отправляет содержимое TXT-файла"""
    if context.user_data.get('state') == 'reading_files':
        document = update.message.document
        if document.mime_type == 'text/plain':
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            text = file_content.decode('utf-8')
            user = update.effective_user
            await logging_request(user, 'reading_txt')
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def reading_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Читает и отправляет содержимое CSV-файла"""
    if context.user_data.get('state') == 'reading_files':
        document = update.message.document
        if document.mime_type == 'text/csv':
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            text = file_content.decode('utf-8')
            csv_data = list(csv.reader(text.splitlines()))
            formatted_csv = "\n".join([", ".join(row) for row in csv_data])
            user = update.effective_user
            await logging_request(user, 'reading_csv')
            await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_csv)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def reading_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Читает и отправляет содержимое JSON-файла"""
    if context.user_data.get('state') == 'reading_files':
        document = update.message.document
        if document.mime_type == 'application/json':
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            text = file_content.decode('utf-8')
            json_data = json.loads(text)
            formatted_json = json.dumps(json_data, indent=4, ensure_ascii=False)
            user = update.effective_user
            await logging_request(user, 'reading_json')
            await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_json)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def create_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание CSV-файла"""
    user = update.effective_user
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для CSV файла (каждая строка должна быть разделена запятыми):")
    await logging_request(user, 'create_csv')
    context.user_data['state'] = 'create_csv'


async def create_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание JSON-файла"""
    user = update.effective_user
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для JSON файла (в формате JSON):")
    await logging_request(user, 'create_json')
    context.user_data['state'] = 'create_json'


async def create_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создание TXT-файла"""
    user = update.effective_user
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для TXT файла:")
    await logging_request(user, 'create_txt')
    context.user_data['state'] = 'create_txt'


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введённого текста"""
    text = update.message.text
    user = update.effective_user
    if not context.user_data.get('state'):
        await logging_request(user, 'handle_message')

    if context.user_data.get('state') == 'create_csv':
        try:
            data = [row.split(',') for row in text.split('\n')]
            with open('output.csv', 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerows(data)
            with open('output.csv', 'rb') as file:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=file)
            os.remove('output.csv')
            context.user_data['state'] = 'menu'
        except Exception as e:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Неправильный формат данных.")

    elif context.user_data.get('state') == 'create_json':
        try:
            json_data = json.loads(text)
            with open('output.json', 'w', encoding='utf-8') as file:
                json.dump(json_data, file, indent=4, ensure_ascii=False)
            with open('output.json', 'rb') as file:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=file)
            os.remove('output.json')
            context.user_data['state'] = 'menu'
        except json.JSONDecodeError:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Неправильный формат данных.")

    elif context.user_data.get('state') == 'create_txt':
        with open('output.txt', 'w', encoding='utf-8') as file:
            file.write(text)
        with open('output.txt', 'rb') as file:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=file)
        os.remove('output.txt')
        context.user_data['state'] = 'menu'


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Привет! 👋 Я многофункциональный бот!\n\n'
                                    '*Список моих возможностей:*\n'
                                    '- Объединение PDF-файлов.\n'
                                    '- Чтение и создание различных типов файлов (TXT, CSV, JSON).\n'
                                    '- Преобразование формата изображений.',
                                    parse_mode='MarkdownV2')
    context.user_data['state'] = 'menu'


if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Обработчики команд
    start_handler = CommandHandler('start', start)
    pdf_merger_start_handler = CommandHandler('pdf_merger', pdf_merger_start)
    format_converter_start_handler = CommandHandler('format_converter', format_converter_start)
    reading_files_handler = CommandHandler('read_files', reading_files)
    create_files_handler = CommandHandler('create_files', create_files)
    create_csv_handler = CommandHandler('create_csv', create_csv)
    create_json_handler = CommandHandler('create_json', create_json)
    create_txt_handler = CommandHandler('create_txt', create_txt)

    # Обработчики документов и сообщений
    pdf_handler_instance = MessageHandler(filters.Document.MimeType("application/pdf"), pdf_handler)
    txt_handler = MessageHandler(filters.Document.MimeType("text/plain"), reading_txt)
    csv_handler = MessageHandler(filters.Document.MimeType("text/csv"), reading_csv)
    json_handler = MessageHandler(filters.Document.MimeType("application/json"), reading_json)
    photo_handler = MessageHandler(filters.PHOTO, photo)
    text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)

    # Регистрация обработчиков
    application.add_handler(start_handler)
    application.add_handler(pdf_merger_start_handler)
    application.add_handler(format_converter_start_handler)
    application.add_handler(reading_files_handler)
    application.add_handler(create_files_handler)
    application.add_handler(create_csv_handler)
    application.add_handler(create_json_handler)
    application.add_handler(create_txt_handler)
    application.add_handler(pdf_handler_instance)
    application.add_handler(txt_handler)
    application.add_handler(csv_handler)
    application.add_handler(json_handler)
    application.add_handler(photo_handler)
    application.add_handler(text_handler)
    application.run_polling()
