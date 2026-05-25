import pdfplumber
import winsound
import re, os
import requests  # Добавлено для HTTP-запросов
import json
import time  # Добавлено для измерения времени

import fitz  # PyMuPDF
import base64
import pdf2image
#import lmstudio as lms


def extract_with_pdfplumber(pdf_path):
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"
    return full_text


def query_local_llm(prompt, max_tokens=20000):
    """
    Отправляет запрос к локальному серверу LM Studio.
    """
    url = "http://localhost:1234/v1/chat/completions"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "model": "local-model",  # Имя модели не важно — сервер сам выберет
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": max_tokens
    }

    try:
        start_time = time.time()  # Засекаем время до запроса
        response = requests.post(url, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        result = response.json()
        end_time = time.time()  # Засекаем время после ответа
        duration = end_time - start_time
        print(f"\nВремя ответа модели: {duration:.2f} секунд")
        print("response:\n", response)
        answer = result['choices'][0]['message']['content'].strip()
        return answer  # Возвращаем и ответ, и время
    except requests.exceptions.RequestException as e:
        return f"[Ошибка подключения к LM Studio: {e}]"


def query_local_llm2(prompt, max_tokens=2000):
    """
    Отправляет запрос к локальному серверу LM Studio.
    """
    url = "http://localhost:1234/v1/chat/completions"
    url = "http://localhost:1234/api/v1/chat"
    headers = {
        "Content-Type": "application/json"
    }

    def encode_image_to_base64(image_path):
        """Кодирует изображение в base64."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Изображение не найдено: {image_path}")
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    base64_image = encode_image_to_base64('image.png')

    #model = "qwen3.5-9b" # 6.5 Gb
    model = "qwen3.5-0.8b" # 1 Gb
    data = {

        "model": model,
        "input": [
            {
            "type": "text",
            "content": prompt
            },
            {
            "type": "image",
            "data_url": f"data:image/png;base64,{base64_image}"
            }
        ],
        "temperature": 0.2
        #"max_tokens": max_tokens
    }

    """    data = {
        "model": "local-model",  # Имя модели не важно — сервер сам выберет
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }
    """

    try:
        start_time = time.time()  # Засекаем время до запроса
        response = requests.post(url, headers=headers, data=json.dumps(data))
        end_time = time.time()  # Засекаем время после ответа
        duration = end_time - start_time
        print(f"\nВремя ответа модели: {duration:.2f} секунд")
        print("response:\n", response)
        response.raise_for_status()
        result = response.json()
        #print(result)
        print("result['output']: ",result['output'])
        answer = result['output'][0]['content'].strip()
        return answer, duration  # Возвращаем и ответ, и время
    except requests.exceptions.RequestException as e:
        return f"[Ошибка подключения к LM Studio: {e}]"


def parse_llm_response_to_json(raw_response):
    """
    Извлекает и парсит JSON из ответа LLM.
    """
    # Удаляем "сырой" текст, оставляя только JSON
    json_str = re.search(r'\{.*\}', raw_response, re.DOTALL)
    if not json_str:
        return None, "JSON не найден"

    try:
        parsed = json.loads(json_str.group(0))
        return parsed, None
    except json.JSONDecodeError as e:
        return None, f"Ошибка парсинга: {e}"


def save_pdf_as_image(pdf_path, output_image_path="image.png"):
    """
    Конвертирует первый лист PDF в изображение и сохраняет как image.png.
    Если файл существует — удаляет его перед сохранением.
    """
    # Удаляем файл, если он существует
    if os.path.exists(output_image_path):
        try:
            os.remove(output_image_path)
            print(f"Файл {output_image_path} был удалён.")
        except PermissionError:
            print(f"Ошибка: не удалось удалить файл {output_image_path}. Возможно, он используется другим процессом.")
            return False

    try:
        # Открываем PDF
        doc = fitz.open(pdf_path)
        page = doc[0]  # Берём первую страницу

        # Рендерим страницу как изображение (повышенное разрешение через матрицу)
        mat = fitz.Matrix(2.0, 2.0)  # Масштаб 2x для лучшего качества
        pix = page.get_pixmap(matrix=mat, dpi=200)

        # Сохраняем как PNG
        pix.save(output_image_path)
        doc.close()

        print(f"PDF сохранён как изображение: {output_image_path}")
        return True

    except Exception as e:
        print(f"Ошибка при конвертации PDF в изображение: {e}")
        return False


def get_protocol_data_3_local_LLM2(full_file_path):
    save_pdf_as_image(full_file_path)

    # === Запрос к локальной модели ===
    #print('len=', len(text))
    #print(text)
    prompt = f"""Тебе передали изображение протокола поверки. В нем надо найти следующие данные:
    заводской номер (он обычно не совпадает с годом производства или владельцем), номер протокола, дата поверки, результат поверки, год изготовления,
    номер в реестре СИ, наименование СИ, владелец, методика поверки, температура окружающей среды,
    влажность, атмосферное давление, ФИО поверителя.
    Найденные данные надо вернуть в формате JSON.  
    Дополнительная информация: дату поверки верни в формате дд.ммм.гггг,
    заводской номер обычно не совпадает с годом производства или владельцем.
    Вернуть надо только параметры, указанные в примере ответа.
    Пример ответа:
{{
    "заводской_номер": "ER140093",
    "номер_протокола": "01/148/26",
    "дата_поверки": "19.01.2026",
    "результат_поверки": "годен",
    "год_изготовления": "2014",
    "Номер_в_реестре_СИ": "48759-11",
    "Наименование_СИ": "Газоанализаторы стационарные ЭРИС-ОПТИМА ПЛЮС",
    "владелец": "ООО «ГАЗПРОМНЕФТЬ-ЯМАЛ",
    "методика_поверки": "МП-242-1237-2011",
    "температура_окружающей_среды": "23,7",
    "влажность": "33,0",
    "атмосферное_давление": "104,0",
    "ФИО_поверителя": "Чупин А.А."  
    }}
    """

    print("\nОтправка запроса к локальной LLM...")
    llm_response, elapsed_time = query_local_llm(prompt)
    print("\nОтвет LLM:")
    print(llm_response)

    json_result, error = parse_llm_response_to_json(llm_response)

    if error:
        print(f"[!] Ошибка: {error}")
        print("Работаем с сырым ответом.")
        structured_result = {"raw": llm_response}
    else:
        print("✅ JSON успешно извлечён:")
        print(json.dumps(json_result, ensure_ascii=False, indent=2))
        structured_result = json_result

    frequency = 1000  # Частота — 1000 Гц
    duration = 700  # Продолжительность — 1000 мс (1 секунда)
    winsound.Beep(frequency, duration)
    return structured_result, 0


def get_protocol_data_3_local_LLM(full_file_path):
    text = extract_with_pdfplumber(full_file_path)
    #print(text)
    # === Запрос к локальной модели ===
    print('len=', len(text))
    #print(text)
    prompt = f"""
Пример:
Текст: 
Общество с ограниченной ответственностью "Многоцелевая Компания. Автоматизация. Исследования. Разработки"
628609 Российская Федерация Ханты-Мансийский Автономный Округ-Югра, г.о Нижневартовск, г Нижневартовск, ул. Индустриальная, зд. 32,
стр. 1, кабинет 14.
Уникальный номер записи об аккредитации в реестре аккредитованных лиц №RA.RU.314356
Протокол периодической поверки
№: 01/148/26 от 19.01.2026
1. Наименование, тип, модификация: Газоанализаторы стационарные
ЭРИС-ОПТИМА ПЛЮС
2. Заводской номер СИ: ER140093
3. Дата выпуска: 2014
4. Регистрационный номер в Федеральном информационном фонде
по обеспечению единства измерений: (cid:9)48759-11
5. Принадлежность: ООО «ГАЗПРОМНЕФТЬ-ЯМАЛ» ИНН 8901001822
6. Наименование нормативного документа по поверке: МП-242-1237-2011
"ГСИ. Газоанализаторы стационарные ЭРИС-ОПТИМА ПЛЮС"
7. Средства поверки/номера паспортов ГС:
Стандартный образец утвержденного типа (метан), паспорт № 01670-25, действителен до 17.02.2027
Стандартный образец утвержденного типа (метан), паспорт № 01668-25, действителен до 17.02.2027
Азот газообразный особой чистоты марки 5.0, № 04991-25, действителен до 11.04.2027
73828.19.1Р.01262800; 73828-19; Калибраторы многофункциональные; ЭЛМЕТРО-Паскаль-03, Паскаль-03; исполнение
ЭЛМЕТРО-Паскаль-03-0,005; № 0414; 2025; 1Р; Эталон 1-го разряда; (свидетельство о поверке № С-ГА/04-03-
2025/415504031 от 04.03.2025 г.; действительно до 03.03.2026 г.)
71394-18; Измерители влажности и температуры; ИВТМ-7 М5-Д; № 96320; (свидетельство о поверке № С-ВСА/02-06-
2025/436974158 от 02.06.2025г.; действительно до 01.06.2026 г.)
19325-12; Ротаметр с местными показаниями; РМ-А-0,063 ГУЗ; № 4091028 ; (свидетельство о поверке № С-АСГ/09-09-
2024/369954110 от 09.09.2024г.; действительно до 08.09.2029 г.)
37469-08; Источники питания постоянного тока импульсные; АКИП-1102; № G372113495; (свидетельство о поверке №
С-ВЯ/26-05-2025/434782673 от 26.05.2025 г.; действительно до 25.05.2026 г.);
Условия поверки:
Температура окружающей среды, ˚С 23,7°С
Относительная влажность окружающей среды, % 33,0%
Атмосферное давление, кПа 104,0 кПа
8. Проведение поверки:
1. Результат внешнего осмотра:
соответствует/не соответствует п. 6.1 методики поверки МП-242-1237-2011
2. Результат опробования:
соответствует/не соответствует п. 6.2 методики поверки МП-242-1237-2011
3. Подтверждение соответствия ПО:
соответствует/не соответствует п. 6.3 методики поверки МП-242-1237-2011
Алгоритм вычисления
Наименование ПО Идентификационное Номер версии (идентификационный номер) Цифровой идентификатор ПО (контрольная цифрового идентификатора
наименование ПО ПО сумма исполняемого кода) ПО
Optima+S/W Optima.hex 4V20 f2c1bf2def4ec38cb9b2fc712f22e1a8 MD5
4. Определение основной погрешности в соответствии с пп. 6.4-6.4.3 методики поверки МП-242-1237-2011:
Погрешность измерения массовой концентрации Измеренное значение Значение
Диапазон измерений массовой (объемной доли) НКПР в ГС Действительное значение массовой концентрации погрешности,
массовой концентрации (объемной доли) метана
концентрации НКПР полученное при
НКПР при подаче i-й ГС,
абсолютной относительной НКПР) вариации
0,00 0,00 0,00 0,00 0,00
-0,33 -0,66 50,52 50,19 0,13
Метан СН4 -0,63 -0,66 95,23 94,60 0,13
(0-100)% НКПР
-1,21 -2,40 50,52 49,31 0,49
0,00 0,00 0,00 0,00 0,00
-0,53 -0,56 95,23 94,70 0,11
Заключение: на основании результатов поверки, СИ признано пригодным/непригодным к применению
Дата поверки: 19 января 2026 г.
Поверитель: Чупин А.А.
(подпись) (фамилия, инициалы)

Ответ:
{{
    "заводской_номер": "ER140093",
    "номер_протокола": "01/148/26",
    "дата_поверки": "19.01.2026",
    "результат_поверки": "годен",
    "год_изготовления": "2014",
    "Номер_в_реестре_СИ": "48759-11",
    "Наименование_СИ": "Газоанализаторы стационарные ЭРИС-ОПТИМА ПЛЮС",
    "владелец": "ООО «ГАЗПРОМНЕФТЬ-ЯМАЛ",
    "методика_поверки": "МП-242-1237-2011",
    "температура_окружающей_среды": "23,7",
    "влажность": "33,0",
    "атмосферное_давление": "104,0",
    "ФИО_поверителя": "Чупин А.А."  
    }}
Дополнительная информация: дату поверки верни в формате дд.ммм.гггг.
Вернуть надо только параметры, указанные в примере ответа.
Теперь обработай этот текст (верни только JSON):
{text}
    """

    print("\nОтправка запроса к локальной LLM...")
    llm_response = query_local_llm(prompt)
    print("\nОтвет LLM:")
    print(llm_response)

    json_result, error = parse_llm_response_to_json(llm_response)

    if error:
        print(f"[!] Ошибка: {error}")
        print("Работаем с сырым ответом.")
        structured_result = {"raw": llm_response}
    else:
        print("✅ JSON успешно извлечён:")
        print(json.dumps(json_result, ensure_ascii=False, indent=2))
        structured_result = json_result

    frequency = 1000  # Частота — 1000 Гц
    duration = 700  # Продолжительность — 1000 мс (1 секунда)
    winsound.Beep(frequency, duration)
    return structured_result, 0
