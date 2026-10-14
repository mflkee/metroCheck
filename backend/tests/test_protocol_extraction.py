"""Регрессионные тесты извлечения полей протокола (реальные фрагменты OCR)."""

from app.services.protocol_extraction_service import ProtocolExtractionService


def make_service() -> ProtocolExtractionService:
    return ProtocolExtractionService()


# ---------------------------------------------------------------------------
# Заказчик (owner)
# ---------------------------------------------------------------------------

TABLE_HEADER_OWNER = """ВНЕШНИЙ ОСМОТР И ОПРОБОВАНИЕ
Замечания по
ТП Номер Класс Владелец Диапазон температуры, ℃ Диаметр электродов, мм Масса, г внешнему
осмотру
ТХА 9475 2 ООО "РИ-ИНВЕСТ" От -40 до 800 0,5 Без замечаний
"""


def test_owner_from_table_row_not_from_header():
    """«Владелец» из шапки таблицы не должен становиться заказчиком."""
    owner = make_service()._extract_owner(TABLE_HEADER_OWNER)
    assert owner == "ООО РИ-ИНВЕСТ"


def test_owner_rejects_legal_entity_marker():
    """«Принадлежность: Юридическое лицо» — это тип, а не название."""
    owner = make_service()._extract_owner("5. Принадлежность: Юридическое лицо")
    assert owner is None


def test_owner_rejects_next_field_label():
    """Пустое «Принадлежащее:» не должно затягивать следующую строку-ярлык."""
    text = "Принадлежащее:\nНормативный документ на методику поверки: МП 0491-1-2016\n"
    assert make_service()._extract_owner(text) is None


def test_owner_strips_inn_and_quotes():
    text = 'Принадлежащее: ООО "РИ-ИНВЕСТ" , ИНН 7705551779'
    assert make_service()._extract_owner(text) == "ООО РИ-ИНВЕСТ"


def test_owner_strips_inn_split_by_ocr_spaces():
    text = "Принадлежащее: ООО «ГАЗПРОМНЕФТЬ-ЯМАЛ» ИНН 8 901001822"
    assert make_service()._extract_owner(text) == "ООО ГАЗПРОМНЕФТЬ-ЯМАЛ"


def test_owner_handles_prinadlezhit_form():
    text = "Принадлежит:\nООО «ГАЗПРОМНЕФТЬ-ЯМАЛ» , ИНН 8901001822"
    assert make_service()._extract_owner(text) == "ООО ГАЗПРОМНЕФТЬ-ЯМАЛ"


# ---------------------------------------------------------------------------
# Заводской номер (serial)
# ---------------------------------------------------------------------------


def test_serial_keeps_short_tail_after_single_letter():
    """«A 59» — это номер, а не номер строки таблицы."""
    text = "Заводской номер: A 59 Год выпуска: 2018"
    assert make_service()._extract_serial_number(text) == "A 59"


def test_serial_compound_from_text():
    text = "Заводской номер (номера): 828-1/828\nГод выпуска: 2015"
    assert make_service()._extract_serial_number(text) == "828-1/828"


def test_serial_compound_from_filename():
    svc = make_service()
    text = "Год выпуска:\n2017\nПринадлежит:"
    assert svc._extract_serial_number(text, "2026-03-10 № S V-K7B65110 (МПИ-5).pdf") == "S V-K7B65110"
    assert svc._extract_serial_number(text, "2026.03.10 № 828-1 828 (МПИ-3).pdf") == "828-1 828"


# ---------------------------------------------------------------------------
# Номер ОТ (mit_number)
# ---------------------------------------------------------------------------

MIT_HEADER_LAYOUT = """ПРОТОКОЛ ПОВЕРКИ № 03/533/26 от 10.03.2026 г.
первичной (периодической) поверки
Наименование прибора Контроллеры программируемые логические MK 201
67996-17
номер по Государственному реестру СИ РФ
Заводской номер: 100201002100088 Год выпуска: 2022
Принадлежность: ООО «ГАЗПРОМНЕФТЬ-ЯМАЛ» ИНН 8901001822
НА.ГНМЦ.0147-17 МП «ГСИ. Контроллеры программируемые логические»
"""

MIT_TWO_SIDED_LAYOUT = """Манометры, вакуумметры и мановакуумметры показывающие, ДМ2005СгУ3
наименование, тип (согласно Гос. реестра СИ РФ), если в состав средства измерений входят несколько автономных блоков
4041-93
номер по Государственному реестру СИ РФ
00627
Средства поверки: 77090.19.1Р.00761951; 77090-19; Преобразователи давления эталонные; ЭЛМЕТРО-Паскаль-04,
"""


def test_mit_after_device_name_beats_methodology_number():
    """Номер ОТ берётся из шапки, а не из «НА.ГНМЦ.0147-17»."""
    assert make_service()._extract_mit_number(MIT_HEADER_LAYOUT) == "67996-17"


def test_mit_not_from_reference_instrument():
    """Номер эталона из «Средства поверки» не должен становиться номером ОТ."""
    assert make_service()._extract_mit_number(MIT_TWO_SIDED_LAYOUT) == "4041-93"


# ---------------------------------------------------------------------------
# Дата поверки (verification_date)
# ---------------------------------------------------------------------------


def test_date_numeric():
    text = "Заключение: СИ признано пригодным\nДата поверки: 01.12.2025 г.\nПоверитель: Иванов И.И."
    assert make_service()._extract_verification_date(text) == "2025-12-01"


def test_date_month_word():
    text = "Заключение: СИ признано пригодным\nДата поверки: 31 марта 2026 г.\nПоверитель: Чупин А.А."
    assert make_service()._extract_verification_date(text) == "2026-03-31"


def test_date_month_word_february():
    text = "Заключение: пригодно\nДата поверки: 18 февраля 2026 г.\nПоверитель: Чупин А.А."
    assert make_service()._extract_verification_date(text) == "2026-02-18"
