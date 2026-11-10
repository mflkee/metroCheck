"""Тесты справочника модификаций и подсказок в проверке."""

from app.services.precheck.common import norm_text
from app.services.precheck.rules import (
    WARNING,
    Context,
    build_successors,
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


def test_parse_modifications_ignores_empty_text():
    assert parse_modifications("Описание типа без перечня исполнений.") == []


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
