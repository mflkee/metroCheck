"""Чтение файлов пачки: xlsm/xlsx (шаблон АРШИН и книга контрагента) и XML импорта."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from openpyxl import load_workbook

from app.services.precheck.common import empty, iso, norm_condition

NS = "{urn://fgis-arshin.gost.ru/module-verifications/import/2020-06-19}"

# шапка -> внутреннее имя (41-колоночный шаблон МКАИР + 57-колоночная книга контрагента)
HEADER_MAP: dict[str, str] = {
    "обозначение си": "ot",
    "заводской номер": "mi_number",
    "инвентарный номер": "inventory_number",
    "поверка по результатам калибровки": "calibration",
    "модификация": "modification",
    "год выпуска": "year_built",
    "си специального назначения": "special_purpose",
    "владелец си": "owner",
    "дата поверки": "vrf_date",
    "действительно до": "valid_date",
    "часовой пояс": "tz",
    "вид поверки": "vrf_type",
    "номер наклейки": "sticker_num",
    "наличие знака поверки в паспорте": "sign_pass",
    "наличие знака поверки на си": "sign_mi",
    "методика поверки": "doc_title",
    "шифр клейма": "sign_cipher",
    "эталоны не гэт с приказом": "etalons_order",
    "эталоны не гэт без приказа": "etalons_noorder",
    "эталоны гэт": "etalons_gpe",
    "гсо": "etalons_gso",
    "си, применяемые в качестве эталона": "etalons",
    "си, применяемые при поверке (не эталоны)": "mis",
    "вещества, применяемые при поверке": "reagents",
    "дополнительные методы": "extra_methods",
    "прочие сведения": "additional_info",
    "поверитель": "verifier",
    "объем проведенной поверки": "scope",
    "протокол": "protocol",
    "протокол поверки": "protocol",
    "№ протокола": "protocol_no",
    "причина непригодности": "bad_reason",
    "температура": "temperature",
    "давление": "pressure",
    "влажность": "humidity",
    # выгрузка реестра из ЛК АРШИН
    "рег. номер типа си": "ot",
    "заводской №/ буквенно-цифровое обозначение": "mi_number",
    "заводской №/буквенно-цифровое обозначение": "mi_number",
    "тип си": "mitype_title",
    "документ": "docnum",
    "статус": "status",
    "пригодность": "applicability",
    "разряд эталона": "rank",
    # книга контрагента (57 колонок)
    "свидетельство": "docnum",
    "ссылка фгис аршин": "arshin_url",
    "мпи предл": "mpi_suggested",
    "мпи прим": "mpi_used",
    "заявка": "application",
    "диапазон": "range",
    "пг": "accuracy",
    "реестр": "registry",
    "наличие": "ot_presence",
    "грси=год": "ot_year_check",
    "если дата некорректна": "date_broken",
    "старое си": "old_si",
}

SUPPORTED = {".xlsm", ".xlsx", ".xml"}


def norm_header(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().replace("ё", "е").split())


def _best_header(rows: list[tuple], limit: int = 10) -> tuple[int, dict[int, str]] | None:
    best: tuple[int, dict[int, str]] | None = None
    for i, row in enumerate(rows[:limit]):
        candidate: dict[int, str] = {}
        for j, value in enumerate(row):
            key = HEADER_MAP.get(norm_header(value))
            if key:
                candidate[j] = key
        if candidate and (best is None or len(candidate) > len(best[1])):
            best = (i, candidate)
    if best and len(best[1]) >= 3:
        return best
    return None


def read_xlsx(data: bytes) -> tuple[list[dict], str]:
    """Прочитать лист с таблицей поверок. Возвращает (записи, имя листа)."""
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    best: tuple[str, list[tuple], tuple[int, dict[int, str]]] | None = None
    try:
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            found = _best_header(rows)
            if found and (best is None or len(found[1]) > len(best[2][1])):
                best = (ws.title, rows, found)
    finally:
        wb.close()
    if best is None:
        raise ValueError("не нашёл лист с шапкой таблицы поверок")

    sheet, rows, (header_idx, mapping) = best
    out: list[dict] = []
    for offset, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
        rec: dict = {"row": offset}
        for j, key in mapping.items():
            if j < len(row):
                rec[key] = row[j]
        if all(empty(rec.get(k)) for k in ("ot", "mi_number", "vrf_date")):
            continue
        _normalize(rec)
        out.append(rec)
    return out, sheet


def _normalize(rec: dict) -> None:
    rec["ot"] = str(rec.get("ot") or "").strip()
    rec["mi_number"] = str(rec.get("mi_number") or "").strip()
    rec["vrf_date"] = iso(rec.get("vrf_date"))
    rec["valid_date"] = iso(rec.get("valid_date"))
    for key in ("owner", "doc_title", "sign_cipher", "modification", "vrf_type", "verifier",
                "bad_reason", "docnum", "mitype_title"):
        if rec.get(key) is not None:
            rec[key] = str(rec[key]).strip()
    rec["year_built"] = str(rec.get("year_built") or "").strip()
    rec["etalons"] = str(rec.get("etalons") or "").strip()
    rec["mis"] = str(rec.get("mis") or "").strip()


def _txt(node: ET.Element | None, path: str, default: str = "") -> str:
    if node is None:
        return default
    found = node.find(path)
    return (found.text or "").strip() if found is not None and found.text else default


def read_xml(data: bytes) -> list[dict]:
    root = ET.fromstring(data)
    out: list[dict] = []
    for i, res in enumerate(root.findall(f"{NS}result"), start=1):
        mi = res.find(f"{NS}miInfo")
        single = mi.find(f"{NS}singleMI") if mi is not None else None
        eta = mi.find(f"{NS}etaMI") if mi is not None else None
        rec: dict = {"row": i}
        if single is not None:
            rec["ot"] = _txt(single, f"{NS}mitypeNumber")
            rec["mitype_title"] = _txt(single, f"{NS}crtmitypeTitle") or _txt(
                single, f"{NS}milmitypeTitle")
            rec["mi_number"] = _txt(single, f"{NS}manufactureNum")
            rec["inventory_number"] = _txt(single, f"{NS}inventoryNum")
            rec["year_built"] = _txt(single, f"{NS}manufactureYear")
            rec["modification"] = _txt(single, f"{NS}modification")
        elif eta is not None:
            rec["ot"] = _txt(eta, f"{NS}primaryRec/{NS}mitypeNumber")
            rec["mi_number"] = _txt(eta, f"{NS}primaryRec/{NS}manufactureNum")
            rec["modification"] = _txt(eta, f"{NS}primaryRec/{NS}modification")
        rec["vrf_date"] = iso(_txt(res, f"{NS}vrfDate"))
        rec["valid_date"] = iso(_txt(res, f"{NS}validDate"))
        vtype = _txt(res, f"{NS}type")
        rec["vrf_type"] = "периодическая" if vtype == "2" else ("первичная" if vtype == "1" else "")
        rec["owner"] = _txt(res, f"{NS}miOwner")
        rec["sign_cipher"] = _txt(res, f"{NS}signCipher")
        rec["doc_title"] = _txt(res, f"{NS}docTitle")
        rec["temperature"] = _txt(res, f"{NS}conditions/{NS}temperature")
        rec["pressure"] = _txt(res, f"{NS}conditions/{NS}pressure")
        rec["humidity"] = _txt(res, f"{NS}conditions/{NS}hymidity")
        rec["additional_info"] = _txt(res, f"{NS}additional_info")
        rec["bad_reason"] = _txt(res, f"{NS}inapplicable/{NS}reasons")
        means = res.find(f"{NS}means")
        if means is not None:
            me = means.find(f"{NS}mieta")
            rec["etalons"] = ", ".join(n.text or "" for n in me.findall(f"{NS}number")) \
                if me is not None else ""
            mis = means.find(f"{NS}mis")
            rec["mis"] = ", ".join(
                f"{_txt(x, f'{NS}typeNum')}/{_txt(x, f'{NS}manufactureNum')}"
                for x in (mis.findall(f"{NS}mi") if mis is not None else [])
            )
        out.append(rec)
    return out


def read_batch(filename: str, data: bytes) -> tuple[list[dict], str]:
    """Прочитать файл по расширению. Возвращает (записи, лист/формат)."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".xml":
        return read_xml(data), "(xml)"
    if suffix in (".xlsm", ".xlsx"):
        return read_xlsx(data)
    raise ValueError(f"неподдерживаемый формат: {suffix or '(без расширения)'}")


def _cell(row: tuple, index: int | None) -> str:
    """Значение ячейки как условие среды («24,5»); пусто, если колонки нет."""
    if index is None or index >= len(row):
        return ""
    return norm_condition(row[index])


def read_input_conditions(data: bytes) -> dict[str, tuple[str, str, str]]:
    """Лист «Ввод» книги контрагента: дата -> (темп, давл, влажн)."""
    try:
        wb = load_workbook(io.BytesIO(data), data_only=True)
    except Exception:  # noqa: BLE001
        return {}
    ws = next((s for s in wb.worksheets if "ввод" in s.title.lower()), None)
    if ws is None:
        wb.close()
        return {}
    rows = list(ws.iter_rows(values_only=True))
    header_idx = None
    for i, row in enumerate(rows[:20]):
        joined = " ".join(norm_header(v) for v in row if v is not None)
        if "темп" in joined and "давл" in joined:
            header_idx = i
            break
    if header_idx is None:
        wb.close()
        return {}
    header = [norm_header(v) for v in rows[header_idx]]
    col_t = next((j for j, h in enumerate(header) if "темп" in h), None)
    col_p = next((j for j, h in enumerate(header) if "давл" in h), None)
    col_h = next((j for j, h in enumerate(header) if "влаж" in h), None)
    out: dict[str, tuple[str, str, str]] = {}
    if col_t is not None:
        for row in rows[header_idx + 1:]:
            day = iso(row[0]) if row else None
            if not day:
                continue
            out[day] = (_cell(row, col_t), _cell(row, col_p), _cell(row, col_h))
    wb.close()
    return out


def looks_like_foreign_name(filename: str) -> bool:
    """Грубая проверка: имя файла не похоже на пачку поверок (сертификат, протокол)."""
    low = filename.lower()
    return bool(re.search(r"сертификат|протокол|паспорт|акт", low))
