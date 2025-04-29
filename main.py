import csv
import io
import json
import logging
import os
import tempfile

import convertapi
import fitz
from PIL import Image
from telegram import Update, InputFile, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN, CONVERTAPI_SECRET
from data import db_session
from data.logging import Logging
from data.users import User

convertapi.api_credentials = CONVERTAPI_SECRET
pdf_files = []

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG
)

logger = logging.getLogger(__name__)


async def logging_request(user, request):
    db_sess = db_session.create_session()
    new_log = Logging(
        applying_user=user.id,  # ID пользователя
        request=request  # Имя запроса
    )
    db_sess.add(new_log)
    db_sess.commit()


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'menu'
    db_sess = db_session.create_session()
    user = update.effective_user
    if not db_sess.query(User).filter(User.account_id == user.id).first():
        new_user = User(
            account_id=user.id,  # ID пользователя
            nickname=user.username,  # username пользователя (@никнейм)
            surname=user.last_name,  # фамилия пользователя (если есть)
            name=user.first_name,  # имя пользователя
        )
        db_sess.add(new_user)
        db_sess.commit()
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
    await logging_request(user, 'help')


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


async def pdf_merger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Готово!"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text=
                                   "Отправьте мне несколько PDF-файлов, и я объединю их в один."
                                   " Когда закончите, нажмите 'Готово!'",
                                   reply_markup=reply_markup)
    pdf_files.clear()
    context.user_data['state'] = 'pdf_merger'


async def reading_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user = update.effective_user
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для CSV файла (каждая строка должна быть разделена запятыми):")
    await logging_request(user, 'create_csv')
    context.user_data['state'] = 'create_csv'


async def create_json(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для JSON файла (в формате JSON):")
    await logging_request(user, 'create_json')
    context.user_data['state'] = 'create_json'


async def create_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Введите данные для TXT файла:")
    await logging_request(user, 'create_txt')
    context.user_data['state'] = 'create_txt'


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
        user = update.effective_user
        await logging_request(user, 'pdf_merger')


async def pdf_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') == 'pdf_merger':
        global pdf_files
        file_id = update.message.document.file_id
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        pdf_files.append(bytes(file_bytes))
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Файл получен. ✅")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def format_converter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['Выйти']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text('Отправьте мне фотографии, и я сконвертирую их в нужный формат. 📸',
                                    reply_markup=reply_markup)
    context.user_data['state'] = 'format_converter_waiting'
    context.user_data['photos_to_convert'] = []


async def image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') != 'format_converter_waiting':
        return
    photos = update.message.photo
    if photos:
        photo_file = await photos[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        file_format = 'jpg'
        try:
            Image.open(io.BytesIO(photo_bytes)).verify()
        except Exception as e:
            await update.message.reply_text(
                'Не удалось обработать изображение. Пожалуйста, попробуйте другой файл. 😥')

        context.user_data['photos_to_convert'].append((photo_bytes, file_format))
    elif update.message.document and update.message.document.mime_type.startswith('image'):
        doc = update.message.document
        photo_file = await context.bot.get_file(doc.file_id)
        photo_bytes = await photo_file.download_as_bytearray()
        file_format = doc.file_name.split('.')[-1].lower()

        try:
            Image.open(io.BytesIO(photo_bytes)).verify()
        except Exception as e:
            await update.message.reply_text('Не удалось обработать изображение. Пожалуйста, попробуйте другой файл. 😥')
            return

        context.user_data['photos_to_convert'].append((photo_bytes, file_format))
    else:
        await update.message.reply_text('Это не изображение. Пожалуйста, отправьте фотографию. 🖼️')
        return

    keyboard = [['PNG', 'JPEG', 'WEBP', 'TIFF', 'SVG'], ['Выйти']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f'Фотографии добавлены в очередь! ✅ Отправьте еще фотографии или выберите формат для конвертации:',
        reply_markup=reply_markup)


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE, format: str):
    photos_to_convert = context.user_data.get('photos_to_convert', [])
    if not photos_to_convert:
        await update.message.reply_text('Не найдено изображение для конвертации.')
        return

    success_count = 0
    failure_messages = []

    for i, (photo_bytes, file_format) in enumerate(photos_to_convert):
        temp_file_path = None
        converted_file_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_format}') as temp_file:
                temp_file.write(photo_bytes)
                temp_file_path = temp_file.name

            try:
                converted_file = convertapi.convert(
                    format, {'File': temp_file_path}
                )
            except convertapi.exceptions.ApiError as e:
                failure_messages.append(
                    f'Не удалось преобразовать фотографию {i + 1}: ConvertAPI не поддерживает конвертацию из {file_format.upper()} в {format.upper()}. 😥')
                continue

            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{format}') as converted_temp_file:
                converted_file_path = converted_temp_file.name
                converted_file.save_files(converted_file_path)

            with open(converted_file_path, 'rb') as f:
                await context.bot.send_document(chat_id=update.effective_chat.id,
                                                document=InputFile(f, filename=f"converted_image_{i + 1}.{format}"))
            success_count += 1

        except Exception as e:
            failure_messages.append(f'Не удалось преобразовать фотографию {i + 1}: {e}')
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

    if success_count > 0:
        await update.message.reply_text(f'Успешно преобразовано {success_count} фото.')
    if failure_messages:
        for msg in failure_messages:
            await update.message.reply_text(msg)

    context.user_data['photos_to_convert'] = []
    context.user_data['state'] = 'format_converter_waiting'

    await update.message.reply_text('Выберите формат для конвертации или отправьте еще фотографии:',
                                    reply_markup=ReplyKeyboardMarkup(
                                        [['PNG', 'JPEG', 'WEBP', 'TIFF', 'SVG'], ['Выйти']], resize_keyboard=True))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    if not context.user_data.get('state') is None:
        db_sess = db_session.create_session()
        if not db_sess.query(User).filter(User.account_id == user.id).first():
            new_user = User(
                account_id=user.id,
                nickname=user.username,
                surname=user.last_name,
                name=user.first_name,
            )
            db_sess.add(new_user)
            db_sess.commit()
    if text == 'Выйти':
        context.user_data['state'] = None
        await update.message.reply_text("Вы вышли из режима конвертации.", reply_markup=ReplyKeyboardRemove())
        return
    if context.user_data.get('state') == 'format_selection':
        if text.upper() in ['PNG', 'JPEG', 'WEBP', 'TIFF', 'SVG']:
            await photo(update, context, text.lower())
            return
    if text.upper() in ['PNG', 'JPEG', 'WEBP', 'TIFF', 'SVG']:
        context.user_data['state'] = 'format_selection'
        await photo(update, context, text.lower())
        return

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
    elif context.user_data.get('state') == 'pdf_merger' and text == "Готово!":
        await merge(update, context)


if __name__ == '__main__':
    db_session.global_init("db/file_bot.db")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler(['start', 'help'], help))
    application.add_handler(MessageHandler(filters.Document.MimeType("application/pdf"), pdf_handler))
    application.add_handler(MessageHandler(filters.Document.MimeType("text/plain"), reading_txt))
    application.add_handler(MessageHandler(filters.Document.MimeType("text/csv"), reading_csv))
    application.add_handler(MessageHandler(filters.Document.MimeType("application/json"), reading_json))
    application.add_handler(CommandHandler('text_converter', reading_files))
    application.add_handler(CommandHandler('file_creator', create_files))
    application.add_handler(CommandHandler('create_csv', create_csv))
    application.add_handler(CommandHandler('create_json', create_json))
    application.add_handler(CommandHandler('create_txt', create_txt))
    application.add_handler(CommandHandler('pdf_merger', pdf_merger))
    application.add_handler(CommandHandler('format_converter', format_converter_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, image_handler))
    application.run_polling()
