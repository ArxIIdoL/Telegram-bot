import csv
import json
import logging
import os

from telegram import Update, ReplyKeyboardRemove, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from config import BOT_TOKEN

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG
)

logger = logging.getLogger(__name__)


async def reading_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'reading_files'
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Отправьте файл (.txt, .csv, .json), а я пришлю его вам сообщением!")


async def create_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'create_files'
    keyboard = [
        ["/create_csv"],
        ["/create_json"],
        ["/create_txt"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите действие:",
                                   reply_markup=reply_markup)


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'menu'
    text = """
    Здравствуйте 👋! Я — телеграм-бот, предназначенный для работы с файлами.
    Вот перечень моих функций:
    \t* Запись нескольких PDF-файлов в один
    \t* Отправка содержимого ваших TXT и CSV файлов
    \t* Отправка всех фотографий из PDF-файлов
    \t* Создание быстрых CSV, JSON и TXT файлов
    \t* Преобразование картинки в черно-белый режим
    \t* Конвертация изображений между форматами.
    """
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=text, reply_markup=ReplyKeyboardRemove())


async def reading_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') == 'reading_files':
        document = update.message.document
        if document.mime_type == 'text/plain':
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            text = file_content.decode('utf-8')
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def reading_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') == 'reading_files':
        document = update.message.document
        if document.mime_type == 'text/csv':
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            text = file_content.decode('utf-8')
            csv_data = list(csv.reader(text.splitlines()))
            formatted_csv = "\n".join([", ".join(row) for row in csv_data])
            await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_csv)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def reading_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') == 'reading_files':
        document = update.message.document
        if document.mime_type == 'application/json':
            file = await document.get_file()
            file_content = await file.download_as_bytearray()
            text = file_content.decode('utf-8')
            json_data = json.loads(text)
            formatted_json = json.dumps(json_data, indent=4, ensure_ascii=False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_json)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def create_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для CSV файла (каждая строка должна быть разделена запятыми):")
    context.user_data['state'] = 'create_csv'


async def create_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для JSON файла (в формате JSON):")
    context.user_data['state'] = 'create_json'


async def create_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для TXT файла:")
    context.user_data['state'] = 'create_txt'


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if context.user_data.get('state') == 'create_csv':
        try:
            data = [row.split(',') for row in text.split('\n')]
            with open('output.csv', 'w', newline='') as file:
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
            with open('output.json', 'w') as file:
                json.dump(json_data, file, indent=4)
            with open('output.json', 'rb') as file:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=file)
            os.remove('output.json')
            context.user_data['state'] = 'menu'
        except json.JSONDecodeError:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Неправильный формат данных.")
    elif context.user_data.get('state') == 'create_txt':
        with open('output.txt', 'w') as file:
            file.write(text)
        with open('output.txt', 'rb') as file:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=file)
        os.remove('output.txt')
        context.user_data['state'] = 'menu'


if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    start_handler = CommandHandler(['start', 'help'], help)
    text_converter_handler = CommandHandler('text_converter', reading_files)
    txt_handler = MessageHandler(filters.Document.MimeType("text/plain"), reading_txt)
    csv_handler = MessageHandler(filters.Document.MimeType("text/csv"), reading_csv)
    json_handler = MessageHandler(filters.Document.MimeType("application/json"), reading_json)
    create_create_files_handler = CommandHandler('file_creator', create_files)
    create_csv_handler = CommandHandler('create_csv', create_csv)
    create_json_handler = CommandHandler('create_json', create_json)
    create_txt_handler = CommandHandler('create_txt', create_txt)
    text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(start_handler)
    application.add_handler(text_converter_handler)
    application.add_handler(txt_handler)
    application.add_handler(csv_handler)
    application.add_handler(json_handler)
    application.add_handler(create_create_files_handler)
    application.add_handler(create_csv_handler)
    application.add_handler(create_json_handler)
    application.add_handler(create_txt_handler)
    application.add_handler(text_handler)
    application.run_polling()