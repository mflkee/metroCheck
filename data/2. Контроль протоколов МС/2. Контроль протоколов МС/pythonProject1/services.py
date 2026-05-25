import os, time, re
import pdfplumber
from datetime import datetime, date
import calendar
import pickle
import requests, json
#from gigachat.models.chat_function_call import ChatFunctionCall
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import pandas as pd
import get_protocol_data_3_local_LLM

API_URL = "https://fgis.gost.ru/fundmetrology/eapi/"


def check_or_create_work_folder(folder_name):
    """Check if a working folder exists, and if not, create it."""
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)


def get_first_and_last_day_for_month(year, month):
    """Возвращает первый и последний день указанного месяца и года."""
    # Первый день месяца
    first_day = date(year, month, 1)

    # Последний день месяца
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    return first_day, last_day


def get_calibrations_count(year, month):
    """Возвращает количество поверок из АРШИНа для указанного месяца и года. Токен не требуется"""
    first_day, last_day = get_first_and_last_day_for_month(year, month)
    url = API_URL + "vri"
    org = 'ООО "МКАИР"'
    params = {
        'verification_date_start': first_day.strftime('%Y-%m-%d'),
        'verification_date_end': last_day.strftime('%Y-%m-%d'),
        'org_title': org,
        'rows': 1
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Проверка на ошибки HTTP

        # Парсим JSON из ответа
        data = response.json()
        print('data count: ', data['result']['count'])
        return int(data['result']['count'])

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при выполнении запроса: {e}")
        return None
    except Exception as e:
        print(f"Ошибка при сохранении данных: {e}")
        return None


def get_calibrations_data(year, month, start, count):
    """Получение данных о поверке из АРШИНА, токен не требуется. """
    first_day, last_day = get_first_and_last_day_for_month(year, month)
    print(f'Получение данных: старт {start}, количество {count}')
    url = API_URL + "vri"
    org = 'ООО "МКАИР"'
    params = {
        'verification_date_start': first_day.strftime('%Y-%m-%d'),
        'verification_date_end': last_day.strftime('%Y-%m-%d'),
        'org_title': org,
        'rows': count,
        'start': start
    }
    max_tryes = 5000
    current_try = 0
    while current_try <=max_tryes:
        current_try += 1
        print(f'Попытка №{current_try}')
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()  # Проверка на ошибки HTTP

            # Парсим JSON из ответа
            data = response.json()
            print('len answer:', len(data['result']['items']))
            return data

        except requests.exceptions.RequestException as e:
            print(f"Ошибка при выполнении запроса: {e}")
            continue
        except Exception as e:
            print(f"Ошибка при сохранении данных: {e}")
            return None


def get_list_calibrations(year, month, folder_name):
    """Получение списка поверок за месяц из АРШИНА. Данные сохраняются в файл step1.bin и step1.xlsx"""
    calibrations_count = get_calibrations_count(year, month)

    current_start = 0

    data = []
    while current_start < calibrations_count:
        step_data = get_calibrations_data(year, month, current_start, 100)
        print(step_data['result']['items'])
        data.extend(step_data['result']['items'])
        current_start += 100

    # Сохраняем данные в файл с помощью pickle
    print('Всего загружено: ', len(data))
    file_path = os.path.join(folder_name, 'step1.bin')

    with open(file_path, 'wb') as f:
        pickle.dump(data, f)

    print(f"Данные успешно сохранены в {file_path}")
    process_calibrations_list(year, month, folder_name)


def process_calibrations_list(year, month, folder_name):
    """Список поверок за месяц из файла step1.bin сохраняется в Excel файл step1.xlsx."""
    file_path = os.path.join(folder_name, 'step1.bin')
    excel_path = os.path.join(folder_name, 'step1.xlsx')

    # Загружаем данные из файла с помощью pickle
    with open(file_path, 'rb') as f:
        data = pickle.load(f)
    # Обработка данных
    print(len(data))
    for item in data:
        print(item)

    # Преобразуем в DataFrame
    df = pd.DataFrame(data)

    # Сохраняем в Excel
    df.to_excel(excel_path, index=False, sheet_name='Calibrations')


def get_data_from_lk(document_number, folder_name):
    """чтение данных с личного кабинета по номеру документа. Нужен токен
      При ошибке запроса кол-во попыток, задержка между попытками
    """
    try_count = 3
    delay_sec = 5
    with open('token.txt', 'r', encoding="utf8") as f:
        token = f.read()

    file_path = os.path.join(folder_name, 'raw_data', document_number.replace('/', '-'))

    current_try = 0
    url = 'https://fgis.gost.ru/fundmetrology/cm/lk/api/rgsprepvriview/2163'
    parameters = {'status': 'PUBLISHED', 'text': document_number}
    st_accept = "application/json, text/plain, */*"

    st_useragent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.4 Safari/605.1.15"
    headers = {"Accept": st_accept, "Accept-Language": "ru,en;q=0.9", "User-Agent": st_useragent,
               "Authorization": token}

    while True:
        response = requests.get(url, params=parameters, headers=headers)
        # print(response.status_code)
        if response.status_code != 200:
            if response.status_code == 401:
                print('Истек срок действия токена. Обновите токен и запустите заново')
                exit()
            print(f'response code: {response.status_code}')
            print('response:\n', response.text)
            current_try += 1
            time.sleep(delay_sec)
            if current_try > try_count:
                return None
        else:
            data = json.loads(response.text)
            data = data['rgsPrepVriViews'][0]
            print(data)
            #with open(file_path, 'wb') as f:
            #    pickle.dump(data, f)
            return data


def get_data_from_lk_for_all_documents(folder_name):
    """Чтение данных с личного кабинета по номеру документа для всех документов.
       Номера документов берутся с файла step1.xlsx. Нужен токен"""
    excel_path = os.path.join(folder_name, 'step1.xlsx')

    # Проверяем, существует ли файл
    if not os.path.exists(excel_path):
        print(f"Файл {excel_path} не найден. Сначала выполните process_calibrations_list.")
        return

    # Читаем исходные данные
    try:
        INPUT_SHEET = 'Calibrations'
        df = pd.read_excel(excel_path, sheet_name=INPUT_SHEET)
    except Exception as e:
        print(f"Ошибка при чтении Excel: {e}")
        return

    # Добавляем флаг обработки, если его нет
    PROCESSED_FLAG_COL = 'processed'  # Дополнительная колонка для отслеживания обработанных строк
    if PROCESSED_FLAG_COL not in df.columns:
        df[PROCESSED_FLAG_COL] = False

    # Определяем, какие строки ещё не обработаны
    unprocessed_rows = df[df[PROCESSED_FLAG_COL] == False].copy()

    print(f"Осталось обработать: {len(unprocessed_rows)} строк")

    results = []
    # Читаем ранее сохранённые результаты, если они есть
    try:
        result_df_existing = pd.read_excel(excel_path, sheet_name='get_ids', dtype={'factoryNum': str})
        results.extend(result_df_existing.to_dict('records'))
        print(f"Загружено ранее сохранённых результатов: {len(result_df_existing)}")
    except Exception:
        print("Ранее сохранённые данные на листе 'get_ids' не найдены. Начинаем с пустого листа.")

    counter = 1
    count = len(unprocessed_rows)
    try:
        for idx, row in unprocessed_rows.iterrows():
            print(f'Обработка {counter} из {count}', end='. ')
            counter += 1
            doc_number = row.get('result_docnum')

            # Пропускаем, если document_number пустой
            if not doc_number or pd.isna(doc_number):
                df.loc[idx, PROCESSED_FLAG_COL] = True
                continue

            # Вызываем функцию
            result = get_data_from_lk(doc_number, folder_name)

            if result is not None:
                results.append(result)
                # Отмечаем строку как обработанную
                df.loc[idx, PROCESSED_FLAG_COL] = True
            else:
                print(f"Сбой при обработке document_number={doc_number}. Остановка. Возобновление при следующем запуске.")
                break

            time.sleep(0.5)  # Чтобы не перегружать внешний источник
    except Exception as e:
        print(f"Ошибка при обработке: {e}")
    finally:
        # Сохраняем обновлённый df (с флагами) обратно в Excel
        OUTPUT_SHEET = 'get_ids'
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=INPUT_SHEET, index=False)
            # Сохраняем результаты
            if results:
                result_df = pd.DataFrame(results)
                result_df.to_excel(writer, sheet_name=OUTPUT_SHEET, index=False)
        print(f"Результаты сохранены в лист '{OUTPUT_SHEET}'")


def get_data2_from_lk(id, document_number, folder_name):
    # При ошибке запроса кол-во попыток, задержка между попытками
    try_count = 3
    delay_sec = 5
    with open('token.txt', 'r', encoding="utf8") as f:
        token = f.read()

    file_path = os.path.join(folder_name, 'raw_data', document_number.replace('/', '-') + '_data2')

    current_try = 0
    url = 'https://fgis.gost.ru/fundmetrology/cm/lk/api/rgsprepvri/2163/' + str(id)
    st_accept = "application/json, text/plain, */*"

    st_useragent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 12_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.4 Safari/605.1.15"
    headers = {"Accept": st_accept, "Accept-Language": "ru,en;q=0.9", "User-Agent": st_useragent,
               "Authorization": token}

    while True:
        response = requests.get(url, headers=headers)
        # print(response.status_code)
        if response.status_code != 200:
            if response.status_code == 401:
                print('Истек срок действия токена. Обновите токен и запустите заново')
                exit()
            print(f'response code: {response.status_code}')
            print('response:\n', response.text)
            current_try += 1
            time.sleep(delay_sec)
            if current_try > try_count:
                return None
        else:
            data = json.loads(response.text)
            if 'miInfo' in data and isinstance(data['miInfo'], dict):
                vri_mi = data['miInfo'].get('vriMi', {})
                # Обновляем корневой словарь элементами из vriMi
                data.update(vri_mi)
                # Удаляем исходный вложенный словарь miInfo, если нужно
                del data['miInfo']
            print(data)
            #with open(file_path, 'wb') as f:
            #    pickle.dump(data, f)
            return data


def get_data2_from_lk_for_all_documents(folder_name):
    excel_path = os.path.join(folder_name, 'step1.xlsx')
    OUTPUT_SHEET = 'get_data'

    # Проверяем, существует ли файл
    if not os.path.exists(excel_path):
        print(f"Файл {excel_path} не найден. Сначала выполните process_calibrations_list.")
        return

    # Читаем исходные данные
    try:
        INPUT_SHEET = 'get_ids'
        df = pd.read_excel(excel_path, sheet_name=INPUT_SHEET)
    except Exception as e:
        print(f"Ошибка при чтении Excel: {e}")
        return

    # Добавляем флаг обработки, если его нет
    PROCESSED_FLAG_COL = 'processed_data2'  # Дополнительная колонка для отслеживания обработанных строк
    if PROCESSED_FLAG_COL not in df.columns:
        df[PROCESSED_FLAG_COL] = False

    # Определяем, какие строки ещё не обработаны
    unprocessed_rows = df[df[PROCESSED_FLAG_COL] == False].copy()

    print(f"Осталось обработать: {len(unprocessed_rows)} строк")

    results = []
    # Читаем ранее сохранённые результаты, если они есть
    try:
        result_df_existing = pd.read_excel(excel_path, sheet_name=OUTPUT_SHEET)
        results.extend(result_df_existing.to_dict('records'))
        print(f"Загружено ранее сохранённых результатов: {len(result_df_existing)}")
    except Exception:
        print("Ранее сохранённые данные на листе 'get_data2' не найдены. Начинаем с пустого листа.")

    counter = 1
    count = len(unprocessed_rows)

    try:
        for idx, row in unprocessed_rows.iterrows():
            print(f'Обработка {counter} из {count}', end='. ')
            counter += 1
            id = row.get('id')
            document_number = row.get('documentTitle')
            print('document_number: ', document_number)

            # Пропускаем, если document_number пустой
            if not id or pd.isna(id):
                df.loc[idx, PROCESSED_FLAG_COL] = True
                continue

            # Вызываем функцию
            result = get_data2_from_lk(id, document_number, folder_name)

            if result is not None:
                results.append(result)
                # Отмечаем строку как обработанную
                df.loc[idx, PROCESSED_FLAG_COL] = True
            else:
                print(f"Сбой при обработке id={id}. Остановка. Возобновление при следующем запуске.")
                break

            time.sleep(0.5)  # Чтобы не перегружать внешний источник

    # Сохраняем обновлённый df (с флагами) обратно в Excel
    finally:
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=INPUT_SHEET, index=False)
            # Сохраняем результаты
            if results:
                result_df = pd.DataFrame(results)
                result_df.to_excel(writer, sheet_name=OUTPUT_SHEET, index=False)
        print(f"Результаты сохранены в лист '{OUTPUT_SHEET}'")


def get_file_creation_time(file_path):
    """Возвращает дату и время создания файла."""
    try:
        # Получаем статистику файла
        stat = os.stat(file_path)
        # На Windows возвращаем время создания
        if os.name == 'nt':
            creation_time = stat.st_ctime
        else:
            # На Unix-системах st_ctime — время последнего изменения метаданных
            # Если доступно, используем st_birthtime (macOS)
            creation_time = getattr(stat, 'st_birthtime', stat.st_ctime)

        return datetime.fromtimestamp(creation_time)
    except Exception as e:
        print(f"Ошибка при получении времени создания файла: {e}")
        return None


def search_protocols(protocol_folder, year, month, work_folder):
    """Ищет протоколы в папке и подпапках и сохраняет их в файл"""
    # Формируем путь к папке: protocol_folder/year/month (месяц с ведущим нулём)
    year_folder = str(year)
    month_folder = f"{month:02d}"
    target_folder = os.path.join(protocol_folder, year_folder, month_folder)

    # Список для хранения найденных файлов
    protocols = []

    # Проверяем, существует ли целевая папка
    if not os.path.exists(target_folder):
        print(f"Папка {target_folder} не существует.")
        return []

    # Обходим целевую папку и все её подпапки
    for root, dirs, files in os.walk(target_folder):
        for file in files:
            file_path = os.path.join(root, file)
            if not file_path.lower().endswith('.pdf'):
                print(f"Пропускаем файл {file_path} — не PDF.")
                continue
            relative_path = os.path.relpath(file_path, protocol_folder)
            file_creation_time = get_file_creation_time(file_path)
            protocols.append({'filename': relative_path, 'creation_time': file_creation_time})

    print(f"Найдено {len(protocols)} файлов в {target_folder}.")

    # Путь к Excel-файлу
    excel_path = os.path.join(work_folder, 'step2.xlsx')

    # Преобразуем список словарей в DataFrame
    df_protocols = pd.DataFrame(protocols)

    # Проверяем, существует ли файл Excel
    if os.path.exists(excel_path):
        # Загружаем существующие листы
        with pd.ExcelFile(excel_path) as xls:
            existing_sheets = {sheet: pd.read_excel(xls, sheet_name=sheet) for sheet in xls.sheet_names}

        # Удаляем лист "Протоколы", если он существует
        if "Протоколы" in existing_sheets:
            del existing_sheets["Протоколы"]

        # Добавляем обновлённый лист с протоколами
        existing_sheets["Протоколы"] = df_protocols

        # Перезаписываем Excel-файл
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            for sheet_name, df_sheet in existing_sheets.items():
                df_sheet.to_excel(writer, sheet_name=sheet_name, index=False)
    else:
        # Если файла нет — создаём новый
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df_protocols.to_excel(writer, sheet_name="Протоколы", index=False)
    return


def union_data(folder_name):
    excel_path = os.path.join(folder_name, 'step1.xlsx')
    output_path = os.path.join(folder_name, 'step2.xlsx')

    if not os.path.exists(excel_path):
        print(f"Файл {excel_path} не найден. Выполните сначала шаги 1-2.")
    else:
        # Читаем все листы
        try:
            df1 = pd.read_excel(excel_path, sheet_name='Calibrations')
            df2 = pd.read_excel(excel_path, sheet_name='get_ids')
            df3 = pd.read_excel(excel_path, sheet_name='get_data')

            mask = df3['notificationNum'].notna()
            founded_indexes = df3[mask].index.tolist()
            for index in founded_indexes:
                df3.at[index, 'certificateNum'] = df3.at[index, 'notificationNum']

            # Переименовываем ключи для объединения
            df1 = df1.rename(columns={'result_docnum': 'document_number'})
            df2 = df2.rename(columns={'documentTitle': 'document_number'})
            df3 = df3.rename(columns={'certificateNum': 'document_number'})

            # Приводим ключ к строковому типу для корректного соединения
            df1['document_number'] = df1['document_number'].astype(str)
            df2['document_number'] = df2['document_number'].astype(str)
            df3['document_number'] = df3['document_number'].astype(str)

            # Объединяем по ключу
            merged = df1.merge(df2, on='document_number', how='outer') \
                .merge(df3, on='document_number', how='outer')

            # Приводим дату к формату datetime
            merged['verification_date'] = pd.to_datetime(merged['verification_date'], format='%d.%m.%Y',
                                                         errors='coerce')
            merged['valid_date'] = pd.to_datetime(merged['valid_date'], format='%d.%m.%Y',
                                                  errors='coerce')
            merged.drop(columns=['verificationDate_x'], inplace=True)
            merged.drop(columns=['mitypeNumber_x'], inplace=True)
            merged.drop(columns=['factoryNum_x'], inplace=True)
            merged.drop(columns=['count'], inplace=True)
            merged.drop(columns=['applicability_y'], inplace=True)
            merged.drop(columns=['status_x'], inplace=True)
            merged.drop(columns=['lastAuthor_x'], inplace=True)

            # Сохраняем результат

            merged.to_excel(output_path, index=False, sheet_name='MergedData')

            print(f"Объединённые данные сохранены в {output_path}")
            print(f"Всего строк: {len(merged)}, столбцов: {len(merged.columns)}")

        except Exception as e:
            print(f"Ошибка при объединении данных: {e}")


def get_protocols_data(type_check, protocol_folder, year, month, folder_name):
    """
    Функция извлекает данные из протоколов поверки
    Надо взять список протоколов из файла step2.xlsx
    Для каждого протокола вызвать функцию get_protocol_data
    и сохранить результат в файл step2.xlsx в листе "Данные_протоколов", добавив к данным имя файла протокола и время
    создания файла. Функция должна возобновлять работу при ошибках, т.е. сохранять промежуточные результаты.
    Также надо сохранить итоговые затраты токенов во вкладку "Затраты"
    type_check - выбор типа загрузки данных из протокола. 1 - используя Гигачат; 2 - ручной сбор данных;
    3 - используя локальную LLM через LLM Studio
    """
    excel_path = os.path.join(folder_name, "step2.xlsx")
    if not os.path.exists(excel_path):
        print(f"Файл {excel_path} не найден.")
        return

    data = {
        'total_tokens': 0,
        'processed_data': []
    }

    # Загружаем список протоколов
    df_protocols = pd.read_excel(excel_path, sheet_name="Протоколы")
    protocols = df_protocols.to_dict('records')

    # Проверяем, есть ли уже обработанные данные
    output_sheet = "Данные_протоколов"
    costs_sheet = "Затраты"

    protocols_count = len(protocols)
    counter = 1

    # Попробуем загрузить уже существующие данные из Excel
    try:
        df_protocols_data = pd.read_excel(excel_path, sheet_name="Данные_протоколов",
                                          dtype={'protocol_number': str, 'serial_number': str})
        data['processed_data'] = df_protocols_data.to_dict('records')
        print(data['processed_data'])
        print(f"Загружены уже обработанные данные {len(data['processed_data'])}")
    except Exception:
        pass  # Листа ещё нет — начнём с нуля

    try:
        df_costs = pd.read_excel(excel_path, sheet_name=costs_sheet)
        if 'total_tokens' in df_costs.columns:
            total_tokens = df_costs.iloc[0]['total_tokens']
            data['total_tokens'] = int(total_tokens) if pd.notna(total_tokens) else 0
            print(f'Загружены затраты токенов: {data["total_tokens"]}')
        else:
            print(f"Столбец 'total_tokens' не найден в листе '{costs_sheet}'.")
    except Exception as e:
        print(f"Ошибка при чтении данных о затратах: {e}")

    try:
        for protocol in protocols:
            print(f"Обработка протокола {counter} из {protocols_count}")
            counter += 1
            file_path = protocol['filename']
            full_file_path = os.path.join(protocol_folder, file_path)
            creation_time = protocol.get('creation_time', None)

            founded = False
            for item in data['processed_data']:
                if item['source_file'] == file_path:
                    print(f"Пропускаем уже обработанный файл: {file_path}")
                    founded = True
                    break
            if founded:
                continue

            print(f"Обработка: {file_path}")
            if type_check==1:
                raise Exception("Not implemented yet!")
            if type_check==2:
                raise Exception("Not implemented yet!")
            if type_check==3:
                result, tokens = get_protocol_data_3_local_LLM.get_protocol_data_3_local_LLM(full_file_path)

            if result is not None:
                # Добавляем метаданные
                result['source_file'] = file_path
                result['file_creation_time'] = creation_time
                data['processed_data'].append(result)

                # Суммируем токены
                data['total_tokens'] += tokens or 0
                print(result)
                print(f"Всего токенов: {data['total_tokens']}")

            else:
                # Сохраняем как None, чтобы не повторять
                data['processed_data'].append({
                    'source_file': file_path,
                    'file_creation_time': creation_time,
                    'error': 'failed_to_extract'
                })
    except KeyboardInterrupt:
        print("Прервано пользователем")
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")

    finally:
        # Сохранение всех данных в Excel
        df_output = pd.DataFrame(data['processed_data'])
        with pd.ExcelWriter(excel_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
            df_output.to_excel(writer, sheet_name=output_sheet, index=False)

        # Сохранение затрат
        costs_df = pd.DataFrame([{
            'total_tokens': data['total_tokens']
        }])
        with pd.ExcelWriter(excel_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
            costs_df.to_excel(writer, sheet_name=costs_sheet, index=False)

        print(f"Обработка завершена. Результаты сохранены в {excel_path}")
        print(f"Итоговые затраты: всего={data['total_tokens']}")




def replace_cyrillic_with_english(text: str) -> str:
    """
    Заменяет русские символы на похожие английские (homoglyphs).
    Используется, например, для обхода фильтров, но будьте осторожны!
    """
    cyr_to_lat = {
        'А': 'A', 'В': 'B', 'Е': 'E', 'К': 'K', 'М': 'M',
        'Н': 'H', 'О': 'O', 'Р': 'P', 'С': 'C', 'Т': 'T',
        'У': 'Y', 'Х': 'X', 'а': 'a', 'е': 'e', 'к': 'k',
        'м': 'm', 'о': 'o', 'р': 'p', 'с': 'c', 'у': 'y',
        'х': 'x'
    }
    return ''.join(cyr_to_lat.get(char, char) for char in text)
def link_arshin_with_protokols(folder_name, year, month):
    """
    Читаем данные из step2.xlsx
    Лист "Данные_протоколов" в один датафрейм
    Лист MergedData в другой датафрейм
    теперь надо соотнести данные из листа "Данные_протоколов" поле serial_number с листом MergedData поле mi_number
    после определения соответствия в датафрейм с листа "Данные_протоколов" добавить поле document_number
    со значением из поля document_number листа MergedData
    :param folder_name:
    :param year:
    :param month:
    :return:
    """
    excel_path = os.path.join(folder_name, "step2.xlsx")

    if not os.path.exists(excel_path):
        print(f"Файл {excel_path} не найден.")
        return

    # Читаем лист "Данные_протоколов", сохраняя строковые типы
    df_protocols = pd.read_excel(excel_path, sheet_name="Данные_протоколов", dtype={'serial_number': str})
    df_protocols['serial_number'] = df_protocols['serial_number'].astype(str).apply(replace_cyrillic_with_english)
    # Читаем лист "MergedData", сохраняя mi_number как строку
    df_arshin = pd.read_excel(excel_path, sheet_name="MergedData", dtype={'mi_number': str, 'document_number': str})
    df_arshin['mi_number'] = df_arshin['mi_number'].astype(str).apply(replace_cyrillic_with_english)

    for index, row in df_protocols.iterrows():
        serial = row['serial_number']
        mask = df_arshin['mi_number'] == serial
        founded_indexes = df_arshin[mask].index.tolist()

        if len(founded_indexes) == 1:
            df_protocols.at[index, 'document_number'] = df_arshin.at[founded_indexes[0], 'document_number']
            df_arshin.at[founded_indexes[0], 'protocol_number'] = row['protocol_number']
            #print("Найдено ровно одно совпадение")
        elif len(founded_indexes) == 0:
            print(f"Не найдено совпадений заводского номера {serial}")
            df_protocols.at[index, 'document_number'] = 'Не найдена запись в Аршине'
        elif len(founded_indexes) > 1:
            print(f"Внимание: найдено {len(founded_indexes)} совпадений — возможны дубли")
            protocol_date = row['protocol_date']
            mask2 = (df_arshin['mi_number'] == serial) & (df_arshin['verification_date'] == protocol_date)
            founded_indexes2 = df_arshin[mask2].index.tolist()
            if len(founded_indexes2) == 1:
                df_protocols.at[index, 'document_number'] = df_arshin.at[founded_indexes2[0], 'document_number']
                df_arshin.at[founded_indexes2[0], 'protocol_number'] = row['protocol_number']
                print(f"Внимание: уточнено по дате поверки")
            elif len(founded_indexes2) == 0:
                print(f"Не найдено совпадений заводского номера {serial}")
                df_protocols.at[index, 'document_number'] = 'Не найдена запись в Аршине'
            else:
                msg=f'К протоколу {row["protocol_number"]} найдено несколько записей в Аршине: '
                for i in founded_indexes2:
                    msg += f'{df_arshin.at[i, "document_number"]}, '

        else:
            print(f"Не найдено совпадений заводского номера {serial}")
            df_protocols.at[index, 'document_number'] = 'Не найдена запись в Аршине'

    # Сохраняем обновлённые DataFrame обратно в Excel
    with pd.ExcelWriter(excel_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
        df_protocols.to_excel(writer, sheet_name='Данные_протоколов', index=False)
        ws1 = writer.sheets['Данные_протоколов']
        ws1.auto_filter.ref = "A1:BZ1"

        df_arshin.to_excel(writer, sheet_name='MergedData', index=False)
        ws2 = writer.sheets['MergedData']
        ws2.auto_filter.ref = "A1:BZ1"

    print("✅ Обновлённые данные сохранены в Excel: 'Данные_протоколов' и 'MergedData'.")


def do_checks(folder_name, year, month):
    """
    Выполняет проверки
    """
    excel_path = os.path.join(folder_name, "step3.xlsx")

    if not os.path.exists(excel_path):
        print(f"Файл {excel_path} не найден.")
        return

    # Читаем лист "Данные_протоколов", сохраняя строковые типы
    df_protocols = pd.read_excel(excel_path, sheet_name="Данные_протоколов", dtype={'serial_number': str})
    # Читаем лист "MergedData", сохраняя mi_number как строку
    df_arshin = pd.read_excel(excel_path, sheet_name="MergedData", dtype={'mi_number': str, 'document_number': str})

    if 'checks_ok' not in df_arshin.columns:
        df_arshin['checks_ok'] = None

    if 'checks_errors' not in df_arshin.columns:
        df_arshin['checks_errors'] = None

    for index, row in df_arshin.iterrows():
        # ищу связанный протокол
        doc_number = row['document_number']
        mask = df_protocols['document_number'] == doc_number
        founded_indexes = df_protocols[mask].index.tolist()

        if len(founded_indexes) != 1:
            print(f"Внимание: найдено {len(founded_indexes)} совпадений — пропускаю этот документ {doc_number}")
            continue
        # сохраняю индекс связанного протокола
        index = founded_indexes[0]

        # проверка соответствия ОТ
        a_ot = row['mit_number']
        p_ot = df_protocols.at[index, 'mit_number']
        if a_ot == p_ot:
            msg = str(df_arshin.at[index, 'checks_ok'])
            if msg is None:
                msg = ''
            msg += 'ОТ; '
            df_arshin.at[index, 'checks_ok'] = msg
        else:
            print(f"❌ ОТ не совпадает {a_ot} != {p_ot}")
            msg = df_arshin.at[index, 'checks_errors']
            if msg is None:
                msg = ''
            msg += 'ОТ; '
            df_arshin.at[index, 'checks_errors'] = msg

        # проверка соответствия даты поверки
        a_date = row['verification_date']
        p_date = df_protocols.at[index, 'protocol_date']
        if a_date == p_date:
            msg = df_arshin.at[index, 'checks_ok']
            if msg is None:
                msg = ''
            msg += 'Дата; '
            df_arshin.at[index, 'checks_ok'] = msg
        else:
            print(f"❌ Даты не совпадает {a_date} != {p_date}")
            msg = df_arshin.at[index, 'checks_errors']
            if msg is None:
                msg = ''
            msg += 'Дата; '
            df_arshin.at[index, 'checks_errors'] = msg

        # проверка поверителя
        a_item = row['verifierName']
        a_item = a_item.replace(' ', '').replace('.', '').upper()
        p_item = df_protocols.at[index, 'verifier']
        p_item = p_item.replace(' ', '').replace('.', '').upper()
        if a_item == p_item:
            msg = df_arshin.at[index, 'checks_ok']
            if msg is None:
                msg = ''
            msg += 'Поверитель; '
            df_arshin.at[index, 'checks_ok'] = msg
        else:
            print(f"❌ Не совпадает {a_item} != {p_item}")
            msg = str(df_arshin.at[index, 'checks_errors'])
            if msg is None:
                msg = ''
            msg += 'Поверитель; '
            df_arshin.at[index, 'checks_errors'] = msg

        # проверка температуры
        a_item = row['conditionsTemperature']
        cleaned = re.sub(r'[^0-9,.]', '', a_item)  # Удаляем всё, кроме цифр и запятой
        a_item = float(cleaned.replace(',', '.'))

        p_item = str(df_protocols.at[index, 'temperature'])
        cleaned = re.sub(r'[^0-9,.]', '', p_item)  # Удаляем всё, кроме цифр и запятой
        p_item = float(cleaned.replace(',', '.'))

        if a_item == p_item:
            msg = df_arshin.at[index, 'checks_ok']
            if msg is None:
                msg = ''
            msg += 'Температура; '
            df_arshin.at[index, 'checks_ok'] = msg
        else:
            print(f"❌ Не совпадает {a_item} != {p_item}")
            msg = str(df_arshin.at[index, 'checks_errors'])
            if msg is None:
                msg = ''
            msg += 'Температура; '
            df_arshin.at[index, 'checks_errors'] = msg

        # проверка давления
        a_item = row['conditionsPressure']
        cleaned = re.sub(r'[^0-9,.]', '', a_item)  # Удаляем всё, кроме цифр и запятой
        a_item = float(cleaned.replace(',', '.'))

        p_item = str(df_protocols.at[index, 'pressure'])
        cleaned = re.sub(r'[^0-9,.]', '', p_item)  # Удаляем всё, кроме цифр и запятой
        p_item = float(cleaned.replace(',', '.'))

        if a_item == p_item:
            msg = df_arshin.at[index, 'checks_ok']
            if msg is None:
                msg = ''
            msg += 'Давление; '
            df_arshin.at[index, 'checks_ok'] = msg
        else:
            print(f"❌ Не совпадает {a_item} != {p_item}")
            msg = str(df_arshin.at[index, 'checks_errors'])
            if msg is None:
                msg = ''
            msg += 'Давление; '
            df_arshin.at[index, 'checks_errors'] = msg


    # Сохраняем обновлённые DataFrame обратно в Excel
    with pd.ExcelWriter(excel_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
        df_arshin.to_excel(writer, sheet_name='MergedData', index=False)
        ws2 = writer.sheets['MergedData']
        ws2.auto_filter.ref = "A1:BZ1"


    print("✅ Обновлённые данные сохранены в Excel: 'Данные_протоколов' и 'MergedData'.")




def get_protocols_data2(protocol_folder, year, month, folder_name):
    """
    Функция извлекает данные из протоколов поверки
    ВЕРСИЯ БЕЗ ГИГАЧАТА
    Надо взять список протоколов из файла step2.xlsx
    Для каждого протокола вызвать функцию get_protocol_data
    и сохранить результат в файл step2.xlsx в листе "Данные_протоколов", добавив к данным имя файла протокола и время
    создания файла. Функция должна возобновлять работу при ошибках, т.е. сохранять промежуточные результаты.
    """
    excel_path = os.path.join(folder_name, "step2.xlsx")
    if not os.path.exists(excel_path):
        print(f"Файл {excel_path} не найден.")
        return

    data = {
        'total_tokens': 0,
        'processed_data': []
    }

    # Загружаем список протоколов
    df_protocols = pd.read_excel(excel_path, sheet_name="Протоколы")
    protocols = df_protocols.to_dict('records')

    # Проверяем, есть ли уже обработанные данные
    output_sheet = "Данные_протоколов"
    costs_sheet = "Затраты"

    protocols_count = len(protocols)
    counter = 1

    # Попробуем загрузить уже существующие данные из Excel
    try:
        df_protocols_data = pd.read_excel(excel_path, sheet_name="Данные_протоколов",
                                          dtype={'protocol_number': str, 'serial_number': str})
        data['processed_data'] = df_protocols_data.to_dict('records')
        print(data['processed_data'])
        print(f"Загружены уже обработанные данные {len(data['processed_data'])}")
    except Exception:
        pass  # Листа ещё нет — начнём с нуля

    try:
        df_costs = pd.read_excel(excel_path, sheet_name=costs_sheet)
        if 'total_tokens' in df_costs.columns:
            total_tokens = df_costs.iloc[0]['total_tokens']
            data['total_tokens'] = int(total_tokens) if pd.notna(total_tokens) else 0
            print(f'Загружены затраты токенов: {data["total_tokens"]}')
        else:
            print(f"Столбец 'total_tokens' не найден в листе '{costs_sheet}'.")
    except Exception as e:
        print(f"Ошибка при чтении данных о затратах: {e}")

    try:
        for protocol in protocols:
            print(f"Обработка протокола {counter} из {protocols_count}")
            counter += 1
            file_path = protocol['filename']
            full_file_path = os.path.join(protocol_folder, file_path)
            creation_time = protocol.get('creation_time', None)

            founded = False
            for item in data['processed_data']:
                if item['source_file'] == file_path:
                    print(f"Пропускаем уже обработанный файл: {file_path}")
                    founded = True
                    break
            if founded:
                continue

            print(f"Обработка: {file_path}")
            result, tokens = get_protocol_data2(full_file_path)

            if result is not None:
                if 'protocol_number' not in result:
                    raise Exception('protocol_number не найден')
                # Добавляем метаданные
                result['source_file'] = file_path
                result['file_creation_time'] = creation_time
                data['processed_data'].append(result)

                # Суммируем токены
                data['total_tokens'] += tokens or 0
                print(result)
                print(f"Всего токенов: {data['total_tokens']}")

            else:
                raise Exception('Данные не получены')
                # Сохраняем как None, чтобы не повторять
                data['processed_data'].append({
                    'source_file': file_path,
                    'file_creation_time': creation_time,
                    'error': 'failed_to_extract'
                })
    except KeyboardInterrupt:
        print("Прервано пользователем")
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")

    finally:
        # Сохранение всех данных в Excel
        df_output = pd.DataFrame(data['processed_data'])
        with pd.ExcelWriter(excel_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
            df_output.to_excel(writer, sheet_name=output_sheet, index=False)

        # Сохранение затрат
        costs_df = pd.DataFrame([{
            'total_tokens': data['total_tokens']
        }])
        with pd.ExcelWriter(excel_path, mode='a', if_sheet_exists='replace', engine='openpyxl') as writer:
            costs_df.to_excel(writer, sheet_name=costs_sheet, index=False)

        print(f"Обработка завершена. Результаты сохранены в {excel_path}")
        print(f"Итоговые затраты: всего={data['total_tokens']}")


def extract_with_pdfplumber(pdf_path):
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            full_text += page.extract_text() + "\n"
    return full_text



