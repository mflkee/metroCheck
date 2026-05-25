import os
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole, Function, FunctionParameters
from dotenv import find_dotenv, load_dotenv


#def delete_attachment(client: GigaChat, attachment_id: str):
def delete_attachment(client, attachment_id: str):
    """Удаляет вложение из GigaChat по attachment_id"""
    try:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        url = f"https://gigachat.devices.sberbank.ru/api/v1/files/{attachment_id}/delete"
        bearer_token = client.get_token()
        payload = {}
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {bearer_token}'
        }
        requests.request("POST", url, headers=headers, data=payload, verify=False)
        print(f"Файл с attachment_id: {attachment_id} успешно удалён с сервера GigaChat")
    except Exception as e:
        print(f"Ошибка при удалении файла с attachment_id {attachment_id}: {e}")


#def upload_attachment(client: GigaChat, file_path: str) -> str:
def upload_attachment(client, file_path: str) -> str:
    """Загружает файл в GigaChat и возвращает attachment_id"""

    try:
        file_id = client.upload_file(open(file_path, "rb"))
        #print(f"Файл загружен: {file_path} → attachment_id: {file_id}")
        return file_id.id_

    except Exception as e:
        print(f"Ошибка при загрузке файла {file_path}: {e}")
        return None


def get_protocol_data_1(client, protocol_file_name):
    """
    Функция извлекает данные из протокола поверки используя LLM GigaChat-Pro
    и сохраняет их. LLM для сохранения данных в файл должен использовать function calling
    Параметры: protocol_file_name - имя файла протокола поверки
    Возвращает: словарь с данными, сформированный вызовом функции save_protocol_data
    """

    # Загрузка клиента GigaChat (учтите, что авторизация должна быть настроена)
    load_dotenv(find_dotenv())
    giga_key = os.getenv('GIGA')

    client = GigaChat(credentials=giga_key, model="GigaChat-Pro", verify_ssl_certs=False)
    #client = GigaChat(credentials=giga_key, model="GigaChat", verify_ssl_certs=False)

    #print(protocol_file_name)
    #text = pdf_to_text_plumber(protocol_file_name)


    attachment_id = upload_attachment(client, protocol_file_name)
    if not attachment_id:
        return None

    # Формируем сообщение для модели
    messages = [
        Messages(
            role=MessagesRole.USER,
            attachments=[attachment_id, ],
            content=f"Тебе передали протокол поверки в виде вложения. "
                    f"Для сохранения данных протокола используется функция save_protocol_data."
                    f"Извлеки из протокола все необходимые данные для функции save_protocol_data,"
                    f"если какая-то из них отсутствует — передай None."
                    f"Далее обязательно вызови её, используя function calling."
            #        f"Если функцию не вызываешь, верни только json. Вот текст протокола: {text}"

        ),
    ]

    save_protocol_data_function = Function(
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
    )

    chat = Chat(messages=messages,
                function_call=ChatFunctionCall(name="save_protocol_data"),
                functions=[save_protocol_data_function]) #,
                #tool_choice={"type": "function", "function": {"name": "save_protocol_data"}} )

    try:
        response = client.chat(chat)
        print(response)
        #print(response.choices[0].message)
        #print("Usage:", response.usage)
        #print(response.choices[0].message.function_call.arguments)
        tokens = response.usage.total_tokens
        #print(f"Всего токенов: {tokens}")
        if response.choices[0].message.function_call is None:
            # Если нет tool_calls, но есть content с кодом — пытаемся извлечь вручную
            content = response.choices[0].message.content
            print('content=', content)
            try:
                # Извлекаем JSON из строки вида save_protocol_data({...})
                json_str = re.search(r"save_protocol_data\((\{.*\})\)", content, re.DOTALL)
                print(json_str)
                #print(json_str.group(1))
                jsn_str = json_str.group(1)
                print(jsn_str)
                jsn_str = jsn_str.replace('<|superquote|>', '"')
                json_str = jsn_str
                # Заменяем возможные «некорректные» кавычки и экранирование
                json_str = json_str.replace('"""', '"').replace("'''", '"')
                json_str = re.sub(r'\n\s*', '', json_str)  # Убираем переносы и лишние пробелы
                json_str = re.sub(r',\s*}', '}', json_str)  # Убираем запятые перед }
                json_str = re.sub(r',\s*\]', ']', json_str)

                # Обработка ключей без кавычек: name=... → "name": ...
                json_str = re.sub(r'(\w+)\s*=', r'"\1": ', json_str)

                # Убираем возможные trailing запятые
                json_str = re.sub(r',(?=[}\]])', '', json_str)

                # Обработка значений со спецсимволами (например, \\" внутри строк)
                json_str = json_str.replace('\\"', '"')
                print(json_str)
                if json_str:
                    args = json.loads(json_str)
                    print(f"✅ Результат получен в json")
                    return args, tokens
            except Exception as e:
                print(f"❌ Не удалось извлечь данные из content: {e}")
            print("Функция не вызвана")
            return None
        else:
            return response.choices[0].message.function_call.arguments, tokens
    except Exception as e:
        print(f"Ошибка при обращении к GigaChat: {e}")
        return None
    finally:
        # Удаляем файл с сервера GigaChat в любом случае
        delete_attachment(client, attachment_id)
        pass
