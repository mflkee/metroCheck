"""Тесты отчёта: разбивка по объектам (схема «месяц × объект»)."""

import io
import zipfile

from app.services.precheck.report import build_report
from app.services.precheck.rules import ERROR, INFO, WARNING, Issue
from app.services.precheck.service import ParsedFile, _object_stats


def _issues() -> list[Issue]:
    return [
        Issue(2, "ОТ", ERROR, "ОТ не найден", "тип не найден", file="август.xlsx"),
        Issue(3, "МПИ", WARNING, "МПИ", "интервал не сходится", file="август.xlsx"),
        Issue(4, "ОТ", WARNING, "ОТ не действует", "срок истёк", file="август.xlsx"),
        Issue(4, "ОТ", INFO, "ОТ распознан", "тип найден", file="август.xlsx"),
        Issue(0, "(файл)", WARNING, "имя файла", "не совпадает", file="август.xlsx"),
    ]


def _parsed() -> list[ParsedFile]:
    return [
        ParsedFile(name="август.xlsx", sheet="Данные", records=[
            {"row": 2, "object": "УКПГ-1"},
            {"row": 3, "object": "УКПГ-1"},
            {"row": 4, "object": "ЦПС"},
        ]),
    ]


def test_object_stats_skips_file_level_issues():
    stats = _object_stats(_parsed(), _issues())
    by_name = {s["name"]: s for s in stats}
    assert by_name["УКПГ-1"] == {"name": "УКПГ-1", "rows": 2, "errors": 1, "warnings": 1}
    assert by_name["ЦПС"] == {"name": "ЦПС", "rows": 1, "errors": 0, "warnings": 1}


def test_object_stats_empty_without_column():
    parsed = [ParsedFile("x.xlsx", "Данные", [{"row": 2}])]
    assert _object_stats(parsed, []) == []


def test_report_contains_objects_section():
    files = [{"name": "август.xlsx", "sheet": "Данные", "rows": 3,
              "errors": 1, "warnings": 2}]
    objects = _object_stats(_parsed(), _issues())
    data = build_report(files, _issues(), "full", objects=objects)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = "".join(z.read(n).decode("utf-8", "ignore")
                       for n in z.namelist() if n.endswith(".xml"))
    assert "Разбивка по объектам" in text
    assert "УКПГ-1" in text
    assert "информация" in text
