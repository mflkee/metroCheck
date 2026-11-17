"""Тесты справочника модификаций и подсказок в проверке."""

from app.services.precheck.common import norm_text
from app.services.precheck.rules import (
    ERROR,
    WARNING,
    Context,
    build_successors,
    mod_key,
    rule_modification,
    rule_ot,
    similar_mods,
)
from app.services.precheck.specs import parse_modifications

SAMPLE = (
    "Приборы измерительные модификаций МП2-У, МП3-У, МП3-Ум, МП3А-У, МП4-У, "
    "МП4-Ум, МП4А-У, ВП2-У, ВП3-У, ВП4-У выпускаются с 2015 года."
)


def test_parse_modifications_from_spec_text():
    names = parse_modifications(SAMPLE)
    assert names[:3] == ["МП2-У", "МП3-У", "МП3-Ум"]
    assert "МП4А-У" in names


def test_parse_modifications_drops_prose_fragments():
    """Фразы из описания не должны попадать в справочник модификаций."""
    text = ("Приборы выпускаются в модификациях МП3-У, которые различаются "
            "быстродействием процессора, МП4-У, по ГОСТ Р 52931-2008, "
            "методом измерений, ВП2-У.")
    names = parse_modifications(text)
    assert names == ["МП3-У", "МП4-У", "ВП2-У"]


def test_parse_modifications_ignores_empty_text():
    assert parse_modifications("Описание типа без перечня исполнений.") == []


METRAN_SPEC = """Датчики имеют следующие модели, различающиеся по метрологическим характери-
стикам, геометрическим размерам, видами технологических соединений, видом измеряемого
давления, основным элементом измерительного механизма:
        -150CG-модель для измерения избыточного давления с тензорезистивным сенсором
или емкостной ячейкой, фланцевое подключение к процессу;
        -150CGR - модель для измерения избыточного давления, с емкостной ячейкой, фланце-
вое подключение к процессу;
        -150TG/150TGR - модели для измерения избыточного давления с тензорезистивным
сенсором, штуцерное подключение к процессу;
        -150TA/150TAR - модели для измерения абсолютного давления с тензорезистивным
сенсором, штуцерное подключение к процессу;
        -150CD - модель для измерения разности давлений с тензорезистивным сенсором или
емкостной ячейкой, фланцевое подключение к процессу;
        -150CDR- модель для измерения разности давлений с емкостной ячейкой, фланцевое
подключение к процессу;
        -150L - датчики гидростатического давления (уровня) с емкостной ячейкой, фланцевое
подключение к процессу.
                                                                               Лист № 2
        Датчики моделей 150CG, 150TG, 150CD, 150TA имеют исполнение АС для применения
на объектах атомной энергетики.
"""


def test_parse_modifications_from_models_list():
    """Перечень моделей строками («-150TG/150TGR - модели …»), а не в абзаце."""
    assert parse_modifications(METRAN_SPEC) == [
        "150CG", "150CGR", "150TG", "150TGR", "150TA", "150TAR",
        "150CD", "150CDR", "150L",
    ]


def test_parse_modifications_ignores_tables():
    """Строки таблиц с допусками не должны попадать в справочник."""
    table = (
        "Таблица 4 - Пределы допускаемой основной приведенной погрешности\n"
        "                     исполнение\n"
        "150CD, 150CG         ±0,0754), ±0,10            -\n"
        "150ТA                    ±0,075                 -\n"
    )
    assert parse_modifications(table) == []


def test_mod_key_unifies_full_and_short_names():
    notation = "Метран-150"
    assert mod_key("Метран-150TG", notation) == mod_key("150TG", notation)
    assert mod_key("Метран-150TGR", notation) != mod_key("150TG", notation)
    assert mod_key("150TG") == "150TG"


def test_rule_modification_accepts_full_name_from_protocol():
    """В протоколе «Метран-150TG», в описании типа — «150TG»: это не ошибка."""
    ctx = Context(
        types={"32854-13": {
            "mods": ["150TG", "150TGR"],
            "notation": "Метран-150",
        }},
        profile="full",
    )
    assert rule_modification(
        {"row": 2, "ot": "32854-13", "modification": "Метран-150TG"}, ctx) == []
    assert rule_modification(
        {"row": 2, "ot": "32854-13", "modification": "Метран-150ZZ"}, ctx) != []


def test_similar_mods_prefers_usage_in_batch():
    """При равном расстоянии выигрывает модификация, которая уже есть в пачке."""
    known = ["МП2-У", "МП3-У", "МП4-У"]
    usage = {("10135-15", norm_text("МП3-У")): 5}
    close = similar_mods("МП9-У", known, usage, "10135-15")
    assert close[0] == ("МП3-У", 1, 5)


def test_similar_mods_lists_variants_when_tied():
    known = ["МП2-У", "МП3-У", "МП4-У"]
    close = similar_mods("МП9-У", known, {}, "10135-15")
    assert {k for k, d, _ in close if d == 1} == {"МП2-У", "МП3-У", "МП4-У"}


def test_rule_modification_suggests_name_used_in_file():
    ctx = Context(
        types={"10135-15": {"mods": ["МП2-У", "МП3-У", "МП4-У"]}},
        mod_usage={("10135-15", norm_text("МП3-У")): 3},
        profile="full",
    )
    issues = rule_modification(
        {"row": 2, "ot": "10135-15", "modification": "МП9-У"}, ctx)
    assert len(issues) == 1
    assert "МП3-У" in issues[0].message
    assert "МП2-У" not in issues[0].message


def test_rule_modification_silent_for_known_name():
    ctx = Context(types={"10135-15": {"mods": ["МП3-У"]}}, profile="full")
    assert rule_modification(
        {"row": 2, "ot": "10135-15", "modification": "мп3-у"}, ctx) == []


def test_build_successors_finds_reapproval():
    """10135-00 → 10135-15: та же основа номера, более поздний срок действия."""
    types = {
        "10135-00": {"valid_to": "2005-05-01"},
        "10135-10": {"valid_to": "2015-04-01"},
        "10135-15": {"valid_to": "2030-04-01"},
        "22234-01": {"valid_to": "2011-01-01"},
    }
    succ = build_successors(types)
    assert succ["10135-00"] == ("10135-15", "2030-04-01")
    assert succ["10135-10"] == ("10135-15", "2030-04-01")
    assert "22234-01" not in succ


def test_rule_ot_expired_renewed_has_own_level():
    """Переутверждённый тип можно держать строже, чем просто истёкший."""
    types = {
        "10135-00": {"title": "Манометры", "valid_to": "2005-05-01"},
        "10135-15": {"title": "Манометры", "valid_to": "2030-04-01"},
    }
    ctx = Context(types=types, successors=build_successors(types),
                  ot_expired="warning", ot_expired_renewed="error", profile="mvp")
    issues = rule_ot({"row": 2, "ot": "10135-00", "vrf_date": "2026-06-01"}, ctx)
    expired = [i for i in issues if i.rule == "ОТ не действует"]
    assert expired and expired[0].level == ERROR


def test_rule_ot_expired_without_successor_uses_base_level():
    types = {"22234-01": {"title": "Манометры", "valid_to": "2011-01-01"}}
    ctx = Context(types=types, successors=build_successors(types),
                  ot_expired="warning", ot_expired_renewed="error", profile="mvp")
    issues = rule_ot({"row": 2, "ot": "22234-01", "vrf_date": "2026-06-01"}, ctx)
    expired = [i for i in issues if i.rule == "ОТ не действует"]
    assert expired and expired[0].level == WARNING


def test_rule_ot_expired_points_to_new_type():
    types = {
        "10135-00": {"title": "Манометры", "valid_to": "2005-05-01"},
        "10135-15": {"title": "Манометры", "valid_to": "2030-04-01"},
    }
    ctx = Context(types=types, successors=build_successors(types),
                  ot_expired="warning", profile="mvp")
    issues = rule_ot({"row": 2, "ot": "10135-00", "vrf_date": "2026-06-01"}, ctx)
    expired = [i for i in issues if i.rule == "ОТ не действует"]
    assert len(expired) == 1
    assert expired[0].level == WARNING
    assert "10135-15" in expired[0].message
    assert "10135-15" in expired[0].hint


def test_rule_ot_missing_offline_is_warning():
    """Без догрузки нельзя утверждать, что типа нет в АРШИН."""
    ctx = Context(types={}, online=False, profile="full")
    issues = rule_ot({"row": 2, "ot": "60967-15", "vrf_date": "2026-06-01"}, ctx)
    assert issues and issues[0].level == WARNING
    assert "не проверялся" in issues[0].message


def test_rule_ot_failed_download_is_warning():
    ctx = Context(types={}, reference_failed={"60967-15"}, profile="full")
    issues = rule_ot({"row": 2, "ot": "60967-15", "vrf_date": "2026-06-01"}, ctx)
    assert issues and issues[0].level == WARNING
    assert "Не удалось загрузить" in issues[0].message


def test_rule_ot_not_found_is_error():
    ctx = Context(types={}, reference_not_found={"60967-15"}, profile="full")
    issues = rule_ot({"row": 2, "ot": "60967-15", "vrf_date": "2026-06-01"}, ctx)
    assert issues and issues[0].level == ERROR
    assert "нет в реестре АРШИН" in issues[0].message
