import argparse, os
import winsound

import services
# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.




# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Скрипт проверки протоколов поверки. Аргументы: год, месяц, номер шага '
                                                 'проверки')
    parser.add_argument('--year', type=int, default=2025, help='Год (например, 2023)')
    parser.add_argument('--month', type=int, default=2, help='Месяц (1-12)')
    parser.add_argument('--step', type=int, default=7, help='Номер шага проверки (1-4). (1 - скачивание '
                                                            'информации о поверенных СИ за выбранный месяц)')

    args = parser.parse_args()
    year = args.year
    month = args.month
    step = args.step
    protocol_folder = 'D:\\WorkDocs\\Метрологическая лаборатория\\2_Документы внутреннего происхождения\\2_19 Протоколы'
    protocol_folder = 'D:\\SynologyDrive\\Метрологическая лаборатория\\2_Документы внутреннего происхождения\\2_19 Протоколы'
    print(f'Год: {year}, Месяц: {month}, Тип проверки: {step}')
    folder_name = f"{year}-{month:02d}"
    # Проверяем, существует ли папка, и создаём, если не существует
    services.check_or_create_work_folder(folder_name)

    if step == 1:
        services.get_list_calibrations(args.year, args.month, folder_name)

    #if step == 2:
    #    services.process_calibrations_list(args.year, args.month, folder_name)

    if step == 3:
        services.get_data_from_lk_for_all_documents(folder_name)

    if step == 4:
        services.get_data2_from_lk_for_all_documents(folder_name)

    if step == 5:
        # объединяем данные
        services.union_data(folder_name)

    if step == 6:
        # ищем протоколы поверки
        services.search_protocols(protocol_folder, year, month, folder_name)

    if step == 7:
        # получаем данные из протоколов с помощью Гигачата
        services.get_protocols_data(protocol_folder, year, month, folder_name)

    if step == 8:
        # соотносим данные из протоколов с выгрузкой из ЛК
        services.link_arshin_with_protokols(folder_name, year, month)

    if step == 9:
        # соотносим данные из протоколов с выгрузкой из ЛК
        services.do_checks(folder_name, year, month)

    frequency = 1000  # Частота — 1000 Гц
    duration = 700  # Продолжительность — 1000 мс (1 секунда)
    winsound.Beep(frequency, duration)

