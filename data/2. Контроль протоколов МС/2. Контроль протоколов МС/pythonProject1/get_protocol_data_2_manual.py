import pdfplumber


def pdf_to_text_plumber(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    except Exception as e:
        print(f"Ошибка: {e}")
    return text.strip()


def get_protocol_data2(protocol_file_name):
    """
    Функция извлекает данные из протокола поверки БЕЗ GigaChat-Pro
    и сохраняет их.
    Параметры: protocol_file_name - имя файла протокола поверки
    Возвращает: словарь с данными, сформированный вызовом функции save_protocol_data
    """

    """save_protocol_data_function = Function(
        name="save_protocol_data",
        description="Сохраняет извлечённые данные из протокола поверки",
        parameters=FunctionParameters(
            type="object",
            properties=
            {
                "protocol_number": {"type": "string", "description": "Номер протокола"},
                "serial_number": {"type": "string", "description": "Серийный (заводской) номер прибора"},
                "year_production": {"type": "string", "description": "Год изготовления прибора"},
                "mit_number": {"type": "string", "description": "Номер по государственному реестру СИ"},
                "name": {"type": "string", "description": "Наименование СИ"},
                "type": {"type": "string", "description": "Тип СИ"},
                "owner": {"type": "string", "description": "Владелец (или принадлежность) СИ , без ИНН, без организационно-правовой формы,"
                                                           "т.е. без ООО, АО и т.д., без слешей"},
                "mi_doc": {"type": "string", "description": "Документ о поверке"},
                "temperature": {"type": "string", "description": "Температура окружающей среды, только число, без "
                                                                 "единиц измерения"},
                "water": {"type": "string", "description": "Относительная влажность воздуха, только число, без единиц"
                                                           " измерения"},
                "pressure": {"type": "string", "description": "Атмосферное давление, только число, без единиц "
                                                              "измерения"},
                "pressure_units": {"type": "string", "enum": ["кПа", "мм.рт.ст"],
                                   "description": "Единицы измерения давления: кПа или мм.рт.ст"},
                "min_range": {"type": "string", "description": "Минимальное значение диапазона измерений, только число,"
                                                               " без единиц измерения"},
                "max_range": {"type": "string", "description": "Максимальное значение диапазона измерений, только "
                                                               "число, без единиц измерения"},
                "units_range": {"type": "string", "description": "Единица измерений диапазона измерений"},
                "protocol_date": {"type": "string", "description": "Дата протокола, в формате ДД.ММ.ГГГГ"},
                "verifier": {"type": "string", "description": "ФИО поверителя"}
            },
            required=[],

            return_parameters=[
                {"type": "object", "properties": {
                    "result": {"type": "string", "description": "Возвращает ОК в случае успешного сохранения данных"}
                }}]
        )
    )"""
    number_reestr_templates = {}
    number_reestr_templates['71842-18'] = {'serial': find_factory_number_1,
                                           'protocol_number': find_protocol_number_1}

    number_reestr_templates['49942-12'] = {'serial': find_factory_number_1,
                                           'protocol_number': find_protocol_number_1}

    number_reestr_templates['10135-00'] = {'serial': find_factory_number_1,
                                           'protocol_number': find_protocol_number_1}


    text = extract_with_pdfplumber(protocol_file_name)
    print(text)

    founded_key = None
    for key, value in number_reestr_templates.items():
        if key in text:
            founded_key = key

    if founded_key is None:
        raise Exception('Не найден номер реестра')
    result = {}
    print('founded key: ', founded_key)
    result['serial_number'] = number_reestr_templates[founded_key]['serial'](text)
    result['protocol_number'] = number_reestr_templates[founded_key]['protocol_number'](text)

    print("Результаты поиска:\n", result)

    input('Нажмите Enter...')



    return result, 0


def get_serial(text):
    pass

    # номер по Государственному реестру СИ РФ
    # 0004931
    # заводской номер (все цифры и буквы заводского номера)
    # Год выпуска: 2019

    return None


def find_factory_number_1(text):
    """
    номер по Государственному реестру СИ РФ
0004931
заводской номер (все цифры и буквы заводского номера)
    """
    lines = text.strip().split('\n')
    for i, line in enumerate(lines):
        if 'заводской номер' in line.lower():
            if i > 0:  # проверяем, что есть предыдущая строка
                prev_line = lines[i - 1].strip()
                return prev_line
    return None


def find_protocol_number_1(text):
    """
Уникальный номер записи об аккредитации в реестре аккредитованных лиц №RA.RU.314356
ПРОТОКОЛ ПЕРИОДИЧЕСКОЙ ПОВЕРКИ №12/028/25
Датчики давления, СУЭР-100-Ех-ДИВ-2335
    """
    lines = text.strip().split('\n')
    key = 'ПРОТОКОЛ ПЕРИОДИЧЕСКОЙ ПОВЕРКИ №'
    for line in lines:
        if key in line:
            return line.split(key, 1)[1].strip()
    return None
