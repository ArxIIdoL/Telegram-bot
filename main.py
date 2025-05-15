import csv
import io
import json
import logging
import os
import tempfile

import convertapi
import fitz
import pandas as pd
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
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
                                   text="Отправьте файл (.txt, .json), а я пришлю его вам сообщением!")


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


async def csv_waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['csv_waiting'] = True
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text="Отправь мне csv файл, и я дам тебе его преобразить!")


CSV_MAX_SIZE_MB, csv_file = 5, None  # Ограничение размера файла в мегабайтах


async def reading_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('csv_waiting'):
        global csv_file
        context.user_data['csv_waiting'], context.user_data['state'] = False, 'csv_manipulation'
        document = update.message.document
        chat_id = update.effective_chat.id

        if not document:
            await context.bot.send_message(chat_id=chat_id, text="Файл не обнаружен.")
            return

        file_obj = await document.get_file()
        file_size_mb = file_obj.file_size / (1024 * 1024)

        if file_size_mb > CSV_MAX_SIZE_MB:
            await context.bot.send_message(chat_id=chat_id,
                                           text=f"Слишком большой файл ({round(file_size_mb)} MB)! "
                                                f"Максимальный размер файла: {CSV_MAX_SIZE_MB} MB.")
            return

        temp_file_path = f"{chat_id}_input.csv"
        await file_obj.download_to_drive(temp_file_path)

        try:
            csv_file = pd.read_csv(temp_file_path)
            await context.bot.send_message(chat_id=chat_id, text="Файл успешно прочитан.")
            await csv_manipulation(update, context)
        except csv_file.errors.EmptyDataError:
            await context.bot.send_message(chat_id=chat_id, text="Файл пуст или поврежден.")
        except csv_file.errors.ParserError:
            await context.bot.send_message(chat_id=chat_id,
                                           text="Проблемы с парсингом файла. Возможно, неверный формат CSV.")
        finally:
            os.remove(temp_file_path)
            user = update.effective_user
            await logging_request(user, 'csv_manipulation')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def csv_manipulation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['state'] = 'csv_manipulation'
    keyboard = [
        ["Выведи первые 10 строк"],
        ["Выведи первые 20 строк"],
        ["Выведи первые 30 строк"],
        ["Выведи последние 10 строк"],
        ["Выведи последние 20 строк"],
        ["Выведи последние 30 строк"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Выберите действие:",
                                   reply_markup=reply_markup)


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
    current_state = context.user_data.get('state')
    if current_state == 'pdf_merger':
        global pdf_files
        file_id = update.message.document.file_id
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        pdf_files.append(bytes(file_bytes))
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Файл получен. ✅")
    elif current_state == 'pdf_images_waiting':
        await pdf_images_handler(update, context)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")


async def format_converter_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['Выйти']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text('Отправьте мне фотографии, и я сконвертирую их в нужный формат. 📸',
                                    reply_markup=reply_markup)
    context.user_data['state'] = 'format_converter_waiting'
    context.user_data['photos_to_convert'] = []
    context.user_data['image_count'] = 0


async def image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (context.user_data.get('state') == 'format_converter_waiting' or
            context.user_data.get('state') == 'image_filter_waiting'):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")
        return


    if context.user_data.get('image_count', 0) >= 5:
        await update.message.reply_text("⚠️ Вы уже отправили максимальное количество изображений (5)!")
        return

    photos = update.message.photo
    if photos:
        photo_bytes = None
        file_format = 'jpg'

        photo_file = await photos[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        try:
            Image.open(io.BytesIO(photo_bytes)).verify()
        except Exception as e:
            await update.message.reply_text(
                'Не удалось обработать изображение. Пожалуйста, попробуйте другой файл. 😥')
            return

        if context.user_data.get('state') == 'format_converter_waiting':
            context.user_data['photos_to_convert'].append((photo_bytes, file_format))
        elif context.user_data.get('state') == 'image_filter_waiting':
            context.user_data['photos_to_filter'].append((photo_bytes, file_format))

        context.user_data['image_count'] += 1

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

        if context.user_data.get('state') == 'format_converter_waiting':
            context.user_data['photos_to_convert'].append((photo_bytes, file_format))
        elif context.user_data.get('state') == 'image_filter_waiting':
            context.user_data['photos_to_filter'].append((photo_bytes, file_format))

        context.user_data['image_count'] += 1

    else:
        await update.message.reply_text('Это не изображение. Пожалуйста, отправьте фотографию. 🖼️')
        return

    remaining = 5 - context.user_data.get('image_count', 0)
    if context.user_data.get('state') == 'format_converter_waiting':
        keyboard = [['PNG', 'JPEG', 'WEBP', 'TIFF', 'SVG'], ['Выйти']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f'Фотографии добавлены в очередь! ✅ Отправьте еще фотографии (осталось {remaining}) или выберите формат для конвертации:',
            reply_markup=reply_markup)
    elif context.user_data.get('state') == 'image_filter_waiting':
        keyboard = [['Чёрно-белый', 'Винтаж',
                     'Негатив', 'Размытие',
                     'Карандашный набросок',
                     'Тёплый свет', 'Холодный свет'], ['Выйти']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        context.user_data['state'] = 'image_filter_waiting'
        await update.message.reply_text(
            f'Фотографии добавлены в очередь! ✅ Отправьте еще фотографии (осталось {remaining}) или выберите фильтр:',
            reply_markup=reply_markup)


async def start_image_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['Выйти']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text('Отправьте мне фотографии, и я изменю их с помощью нужного фильтра. 📸',
                                    reply_markup=reply_markup)
    context.user_data['state'] = 'image_filter_waiting'
    context.user_data['photos_to_filter'] = []
    context.user_data['image_count'] = 0


async def convert_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, format: str):
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

    await update.message.reply_text('Отправьте мне фотографии, и я сконвертирую их в нужный формат. 📸',
                                    reply_markup=ReplyKeyboardMarkup(
                                        [['PNG', 'JPEG', 'WEBP', 'TIFF', 'SVG'], ['Выйти']], resize_keyboard=True))
    context.user_data['image_count'] = 0



async def image_filter(update: Update, context: ContextTypes.DEFAULT_TYPE, format: str):
    # Вспомогательные функции для эффектов
    def apply_vintage_effect(img):
        """Применяет винтажный эффект к изображению"""
        converter = ImageEnhance.Color(img)
        img = converter.enhance(0.5)
        sepia = img.convert("RGB")
        width, height = img.size
        pixels = sepia.load()
        for py in range(height):
            for px in range(width):
                r, g, b = sepia.getpixel((px, py))
                tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                pixels[px, py] = (min(tr, 255), min(tg, 255), min(tb, 255))
        return sepia

    def apply_pencil_sketch(img):
        """Преобразует изображение в карандашный набросок"""
        gray_img = img.convert('L')
        inverted_img = ImageOps.invert(gray_img)
        blurred_img = inverted_img.filter(ImageFilter.GaussianBlur(radius=3))
        return ImageOps.invert(blurred_img)

    def apply_warm_light(img):
        """Добавляет теплый свет (желтоватый оттенок)"""
        r, g, b = img.split()
        r = r.point(lambda i: min(255, int(i * 1.2)))
        g = g.point(lambda i: min(255, int(i * 1.1)))
        return Image.merge('RGB', (r, g, b))

    def apply_cold_light(img):
        """Добавляет холодный свет (голубоватый оттенок)"""
        r, g, b = img.split()
        g = g.point(lambda i: min(255, int(i * 1.1)))
        b = b.point(lambda i: min(255, int(i * 1.2)))
        return Image.merge('RGB', (r, g, b))

    photos_to_use_filter = context.user_data.get('photos_to_filter', [])
    if not photos_to_use_filter:
        await update.message.reply_text('Не найдено изображение для конвертации.')
        return

    success_count = 0
    failure_messages = []
    user = update.effective_user

    for i, (photo_bytes, file_format) in enumerate(photos_to_use_filter):
        try:
            # Обрабатываем изображение в памяти
            with Image.open(io.BytesIO(photo_bytes)) as img:
                # Применяем выбранный фильтр
                if format == 'Чёрно-белый':
                    processed_img = img.convert('L')
                    await logging_request(user, 'filter_bw_apply')
                elif format == 'Винтаж':
                    processed_img = apply_vintage_effect(img)
                    await logging_request(user, 'filter_vintage_apply')
                elif format == 'Негатив':
                    processed_img = ImageOps.invert(img.convert('RGB'))
                    await logging_request(user, 'filter_negative_apply')
                elif format == 'Размытие':
                    processed_img = img.filter(ImageFilter.BLUR)
                    await logging_request(user, 'filter_blur_apply')
                elif format == 'Карандашный набросок':
                    processed_img = apply_pencil_sketch(img)
                    await logging_request(user, 'filter_sketch_apply')
                elif format == 'Тёплый свет':
                    processed_img = apply_warm_light(img)
                    await logging_request(user, 'filter_warm_apply')
                elif format == 'Холодный свет':
                    processed_img = apply_cold_light(img)
                    await logging_request(user, 'filter_cold_apply')

                # Сохраняем в бинарный поток
                output = io.BytesIO()
                processed_img.save(output, format='JPEG' if file_format.lower() == 'jpg' else file_format.upper())
                output.seek(0)

                # Отправляем обработанное изображение
                await update.message.reply_photo(photo=output)
                success_count += 1

        except Exception as e:
            failure_messages.append(f"Ошибка при обработке фото {i + 1}: {str(e)}")

    if success_count > 0:
        await update.message.reply_text(f'Успешно преобразовано {success_count} фото.')
    if failure_messages:
        for msg in failure_messages:
            await update.message.reply_text(msg)
    context.user_data['state'] = 'image_filter_waiting'


async def pdf_images_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['Готово'], ['Выйти']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text('Отправьте мне PDF-файл(ы), и я извлеку из них изображения.',
                                    reply_markup=reply_markup)
    context.user_data['state'] = 'pdf_images_waiting'
    context.user_data['pdf_files'] = []


async def pdf_images_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') != 'pdf_images_waiting':
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Сначала нужно выбрать режим!")
        return
    document = update.message.document
    if document.mime_type == 'application/pdf':
        file_id = document.file_id
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        context.user_data['pdf_files'].append(file_bytes)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Файл получен. ✅")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Это не PDF-файл. Пожалуйста, отправьте PDF-файл. 📄")


async def extract_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pdf_files = context.user_data.get('pdf_files', [])
    if not pdf_files:
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text="Нет файлов для обработки. 😔 Отправьте PDF-файлы.",
                                       reply_markup=ReplyKeyboardRemove())
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Извлекаю изображения... ⏳",
                                   reply_markup=ReplyKeyboardRemove())
    user = update.effective_user
    await logging_request(user, 'pdf_images')
    for pdf_file in pdf_files:
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(pdf_file)
                temp_file_path = temp_file.name

            doc = fitz.open(temp_file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                images = page.get_images(full=True)
                for img in images:
                    xref = img[0]
                    base_image = doc.extract_image(xref)

                    if base_image is None:
                        continue

                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    image_filename = f"image_{page_num + 1}_{xref}.{image_ext}"

                    with open(image_filename, "wb") as image_file:
                        image_file.write(image_bytes)

                    with open(image_filename, "rb") as image_file:
                        await context.bot.send_document(chat_id=update.effective_chat.id, document=image_file)

                    os.remove(image_filename)

            doc.close()
            os.remove(temp_file_path)
        except Exception as e:
            await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text=f"Произошла ошибка при обработке файла: {e} 😢")
        finally:
            if temp_file:
                try:
                    os.remove(temp_file.name)
                except Exception as e:
                    pass

    context.user_data['pdf_files'] = []
    # context.user_data['state'] = None
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Извлечение изображений завершено! 📸")
    keyboard = [['Готово'], ['Выйти']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text('Отправьте мне PDF-файл(ы), и я извлеку из них изображения.',
                                    reply_markup=reply_markup)
    context.user_data['state'] = 'pdf_images_waiting'
    context.user_data['pdf_files'] = []


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    if context.user_data.get('state') != 'image_filter_waiting':
        context.user_data['photos_to_filter'] = []
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
        context.user_data['photos_to_filter'] = []
        await update.message.reply_text("Вы вышли из режима.", reply_markup=ReplyKeyboardRemove())
        return
    if text == 'Готово':
        await extract_images(update, context)
        return
    if context.user_data.get('state') == 'format_selection':
        if text.upper() in ['PNG', 'JPEG', 'WEBP', 'TIFF', 'SVG']:
            await convert_photo(update, context, text.lower())
            return
    if text.upper() in ['PNG', 'JPEG', 'WEBP', 'TIFF', 'SVG']:
        context.user_data['state'] = 'format_selection'
        await convert_photo(update, context, text.lower())
        return

    if context.user_data.get('state') == 'create_csv':
        await logging_request(user, 'create_csv')
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
        await logging_request(user, 'create_json')
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
        await logging_request(user, 'create_txt')
        with open('output.txt', 'w') as file:
            file.write(text)
        with open('output.txt', 'rb') as file:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=file)
        os.remove('output.txt')
        context.user_data['state'] = 'menu'
    elif context.user_data.get('state') == 'pdf_merger' and text == "Готово!":
        await merge(update, context)
    elif context.user_data.get('state') == 'csv_manipulation':
        global csv_file
        if text == "Выведи первые 10 строк":
            first_rows = csv_file.head(10).to_string(index=False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"<pre>{first_rows}</pre>",
                                           parse_mode='HTML')
        elif text == "Выведи первые 20 строк":
            first_rows = csv_file.head(20).to_string(index=False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"<pre>{first_rows}</pre>",
                                           parse_mode='HTML')

        elif text == "Выведи первые 30 строк":
            first_rows = csv_file.head(30).to_string(index=False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"<pre>{first_rows}</pre>",
                                           parse_mode='HTML')

        elif text == "Выведи последние 10 строк":
            last_rows = csv_file.tail(10).to_string(index=False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"<pre>{last_rows}</pre>",
                                           parse_mode='HTML')

        elif text == "Выведи последние 20 строк":
            last_rows = csv_file.tail(20).to_string(index=False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"<pre>{last_rows}</pre>",
                                           parse_mode='HTML')

        elif text == "Выведи последние 30 строк":
            last_rows = csv_file.tail(30).to_string(index=False)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"<pre>{last_rows}</pre>",
                                           parse_mode='HTML')

    elif context.user_data.get('state') == 'image_filter_waiting' and text in ['Чёрно-белый', 'Винтаж',
                                                                               'Негатив', 'Размытие',
                                                                               'Карандашный набросок',
                                                                               'Тёплый свет', 'Холодный свет']:
        await image_filter(update, context, text)


if __name__ == '__main__':
    db_session.global_init("db/file_bot.db")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler('pdf_images', pdf_images_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler(['start', 'help'], help))
    application.add_handler(MessageHandler(filters.Document.MimeType("application/pdf"), pdf_handler))
    application.add_handler(MessageHandler(filters.Document.MimeType("text/plain"), reading_txt))
    application.add_handler(MessageHandler(filters.Document.MimeType("application/json"), reading_json))

    application.add_handler(CommandHandler('image_filter', start_image_filter))

    application.add_handler(CommandHandler('text_converter', reading_files))
    application.add_handler(CommandHandler('file_creator', create_files))
    application.add_handler(CommandHandler('create_csv', create_csv))
    application.add_handler(CommandHandler('create_json', create_json))
    application.add_handler(CommandHandler('create_txt', create_txt))
    application.add_handler(CommandHandler('pdf_merger', pdf_merger))
    application.add_handler(CommandHandler('format_converter', format_converter_start))
    application.add_handler(MessageHandler(filters.Document.MimeType("text/csv"), reading_csv))
    application.add_handler(CommandHandler('csv_manipulation', csv_waiting))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, image_handler))
    application.run_polling()
