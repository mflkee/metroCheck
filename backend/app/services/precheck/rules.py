"""Правила проверки пачки перед загрузкой в АРШИН.

Правило — функция(record, ctx) -> list[Issue]. Набор расширяется добавлением функции
в RULES; профиль `mvp` содержит только требования ТЗ (МПИ и корректность ОТ).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.precheck.common import (
    empty,
    levenshtein,
    meth_core,
    mpi_valid_until,
    norm_condition,
    norm_number,
    norm_text,
    used_months,
)

ERROR, WARNING, INFO = "ошибка", "предупреждение", "инфо"


@dataclass
class Issue:
    row: int
    column: str
    level: str
    rule: str
    message: str
    hint: str = ""
    file: str = ""


@dataclass
class Context:
    """Данные для правил: справочник типов, условия по датам, настройки."""

    types: dict[str, dict] = field(default_factory=dict)
    previous: dict[tuple[str, str], list[dict]] = field(default_factory=dict)
    conditions_by_date: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    profile: str = "mvp"
    mpi_mode: str = "any"
    ot_expired: str = "warning"
    allowed_ciphers: set[str] = field(default_factory=set)
    today: str = ""
    batch_index: dict[tuple[str, str], list[int]] = field(default_factory=dict)


# --------------------------------------------------------------- правила
def rule_required(r: dict, ctx: Context) -> list[Issue]:
    out: list[Issue] = []
    checks = [
        ("ot", "ОТ (обозначение СИ)", "нет номера типа СИ — запись не пройдёт импорт"),
        ("vrf_date", "Дата поверки", "обязательное поле"),
        ("vrf_type", "Вид поверки", "в XSD обязательно: 1 — первичная, 2 — периодическая"),
        ("owner", "Владелец СИ", "обязательное поле (miOwner)"),
        ("sign_cipher", "Шифр клейма", "обязательное поле (signCipher)"),
        ("doc_title", "Методика поверки", "обязательное поле (docTitle)"),
    ]
    for key, col, why in checks:
        if empty(r.get(key)):
            out.append(Issue(r["row"], col, ERROR, "обязательное поле",
                             f"поле не заполнено: {why}"))
    if empty(r.get("mi_number")) and empty(r.get("inventory_number")):
        out.append(Issue(r["row"], "Заводской/Инвентарный номер", ERROR, "обязательное поле",
                         "нужен заводской или инвентарный номер"))
    if empty(r.get("etalons")) and empty(r.get("mis")):
        out.append(Issue(r["row"], "Средства поверки", ERROR, "обязательное поле",
                         "не указаны средства поверки (эталоны / СИ при поверке)"))
    for key, col in (("temperature", "Температура"), ("pressure", "Давление"),
                     ("humidity", "Влажность")):
        if empty(r.get(key)):
            out.append(Issue(r["row"], col, ERROR, "обязательное поле",
                             "условия поверки обязательны по XSD"))
    return out


def rule_ot(r: dict, ctx: Context) -> list[Issue]:
    out: list[Issue] = []
    ot = (r.get("ot") or "").strip()
    if not ot:
        return out
    card = ctx.types.get(ot)
    if card is None:
        out.append(Issue(r["row"], "ОТ", ERROR, "ОТ не найден",
                         f"тип СИ {ot} отсутствует в справочнике и не найден в реестре",
                         "проверьте номер: частая ошибка — «протянутая» последняя цифра"))
        return out
    if card.get("title"):
        out.append(Issue(r["row"], "ОТ", INFO, "ОТ распознан",
                         f"{ot} — {card['title']}"
                         + (f", обозн. {card['notation']}" if card.get("notation") else "")))
    valid_to = card.get("valid_to")
    if valid_to and r.get("vrf_date") and valid_to < r["vrf_date"]:
        level = {"error": ERROR, "warning": WARNING}.get(ctx.ot_expired)
        if level:
            out.append(Issue(r["row"], "ОТ", level, "ОТ не действует",
                             f"утверждение типа {ot} действовало до {valid_to}, "
                             f"а поверка — {r['vrf_date']}",
                             "уточните, не должен ли использоваться переутверждённый ОТ"))
    return out


def _mpi_applies(mpi: dict, year_built: object) -> bool | None:
    """Условие «изготовленных с/до <дата>» против года выпуска прибора."""
    param = (mpi.get("parameter") or "").lower()
    if not param or not year_built:
        return None
    try:
        year = int(str(year_built)[:4])
    except (TypeError, ValueError):
        return None
    m = re.search(r"изготовленн\w*\s+(с|до|после)\s+(\d{1,2})\s+([а-я]+)\s+(\d{4})", param)
    if m:
        prep, cut = m.group(1), int(m.group(4))
    else:
        m = re.search(r"изготовленн\w*\s+(с|до|после)\s+(\d{4})-(\d{2})-(\d{2})", param)
        if not m:
            return None
        prep, cut = m.group(1), int(m.group(2))
    if year == cut:
        return None
    return year < cut if prep == "до" else year > cut


def rule_mpi(r: dict, ctx: Context) -> list[Issue]:
    out: list[Issue] = []
    ot = (r.get("ot") or "").strip()
    card = ctx.types.get(ot)
    vrf = r.get("vrf_date")
    if not card or not vrf:
        return out

    # непригодное СИ: «действительно до» не заполняется
    if not empty(r.get("bad_reason")):
        if r.get("valid_date"):
            out.append(Issue(r["row"], "Действительно до", WARNING, "МПИ",
                             "СИ непригодно, но заполнена дата «действительно до»",
                             "для извещения о непригодности дата не указывается"))
        return out

    rows = card.get("mpi") or []
    if not rows:
        if r.get("valid_date"):
            out.append(Issue(r["row"], "Действительно до", WARNING, "МПИ не установлен",
                             "для этого типа нет периодической поверки, а дата заполнена"))
        return out

    def in_period(m: dict) -> bool:
        return (not m.get("valid_from") or m["valid_from"] <= vrf) and \
               (not m.get("valid_to") or vrf <= m["valid_to"])

    cand = [m for m in rows if in_period(m)] or rows
    if ctx.mpi_mode == "strict":
        narrowed = [m for m in cand if _mpi_applies(m, r.get("year_built")) is not False]
        if narrowed:
            cand = narrowed

    real = r.get("valid_date")
    periodic = norm_text(r.get("vrf_type")) in ("2", "ПЕРИОДИЧЕСКАЯ", "ПЕРИОДИЧЕСКИЙ") \
        or (not r.get("vrf_type") and bool(real))

    if all(m.get("months") is None for m in cand):
        if real:
            out.append(Issue(r["row"], "Действительно до", WARNING, "МПИ не установлен",
                             "у типа предусмотрена только первичная поверка — "
                             "дату заполнять не нужно"))
        return out

    expected = [(m, mpi_valid_until(vrf, int(m["months"]))) for m in cand if m.get("months")]
    if not expected:
        return out

    if not real:
        if periodic:
            exp = ", ".join(sorted({e for _, e in expected}))
            out.append(Issue(r["row"], "Действительно до", ERROR, "МПИ",
                             f"для периодической поверки дата обязательна (ожидается {exp})",
                             "если СИ признано непригодным — заполните «Причину непригодности»"))
        return out

    if any(e == real for _, e in expected):
        m = next(m for m, e in expected if e == real)
        out.append(Issue(r["row"], "Действительно до", INFO, "МПИ",
                         f"сходится: {m['months']} мес → {real}"
                         + (f" (условие: {m['parameter']})" if m.get("parameter") else "")))
        return out

    used = used_months(vrf, real)
    expected_text = "; ".join(
        f"{m['months']} мес → {e}" + (f" ({m['parameter']})" if m.get("parameter") else "")
        for m, e in expected)
    actual_text = f"указано {used} мес (до {real})" if used else f"указано до {real}"
    out.append(Issue(r["row"], "Действительно до", ERROR, "МПИ",
                     f"{actual_text}, а в карточке типа — {expected_text}",
                     "проверьте интервал и дату"))
    return out


def rule_reverify(r: dict, ctx: Context) -> list[Issue]:
    """Поверка раньше окончания предыдущей (данные передаются в ctx.previous)."""
    out: list[Issue] = []
    ot = (r.get("ot") or "").strip()
    mi = r.get("mi_number") or r.get("inventory_number")
    vrf = r.get("vrf_date")
    if not ot or not mi or not vrf or not ctx.previous:
        return out
    prev = ctx.previous.get((ot, norm_number(mi))) or []
    for p in prev:
        valid = p.get("valid_date")
        if valid and valid >= vrf:
            out.append(Issue(r["row"], "Дата поверки", WARNING, "повторная поверка",
                             f"поверка раньше окончания предыдущей (та действовала до {valid})",
                             "для отдельных владельцев (ИНК) допускается"))
            break
    return out


def rule_method(r: dict, ctx: Context) -> list[Issue]:
    """Методика поверки: существует у типа, действует на дату и та ли редакция.

    Ловит именно случай «в описании типа поменялась методика»: в карточке появляется
    новая редакция (новый приказ), а в файле остаётся старая.
    """
    out: list[Issue] = []
    ot = (r.get("ot") or "").strip()
    card = ctx.types.get(ot)
    doc = (r.get("doc_title") or "").strip()
    if not card or not doc:
        return out

    placeholder = {"МЕТОДИКИПОВЕРКИ", "МЕТОДИКАПОВЕРКИ", "МЕТОДИКИ", "-", ""}
    meth = [m for m in (card.get("meth") or [])
            if (m.get("dec_num") or "").strip() or norm_text(m.get("title")) not in placeholder]
    if not meth:
        return out

    vrf = r.get("vrf_date") or ctx.today

    def label(m: dict) -> str:
        code = (m.get("dec_num") or m.get("title") or "").strip()[:60]
        if m.get("valid_from") and m.get("valid_to"):
            return f"{code} (с {m['valid_from']} до {m['valid_to']})"
        if m.get("valid_from"):
            return f"{code} (с {m['valid_from']})"
        if m.get("valid_to"):
            return f"{code} (до {m['valid_to']})"
        return code

    def valid_at(m: dict, day: str) -> bool:
        return (not m.get("valid_from") or m["valid_from"] <= day) and \
               (not m.get("valid_to") or day <= m["valid_to"])

    base_in, edition_in = meth_core(doc)
    same: list[tuple[dict, str]] = []
    for m in meth:
        for value in (m.get("dec_num"), m.get("title")):
            if not value:
                continue
            base, edition = meth_core(value)
            if base and base_in and (base == base_in or base.startswith(base_in)
                                     or base_in.startswith(base)):
                same.append((m, edition))
                break

    if not same:
        allowed = "; ".join(label(m) for m in meth)
        return [Issue(r["row"], "Методика поверки", ERROR, "методика",
                      f"«{doc}» не найдена в карточке типа {ot}",
                      f"в карточке: {allowed}")]

    # выбираем редакцию, действовавшую на дату поверки; если такой нет — ближайшую
    applicable = [(m, e) for m, e in same if valid_at(m, vrf)]
    if applicable:
        chosen, edition_card = applicable[-1]
    else:
        newer = [(m, e) for m, e in same
                 if m.get("valid_from") and m["valid_from"] > vrf]
        chosen, edition_card = newer[0] if newer else same[0]

    problems: list[Issue] = []

    if not valid_at(chosen, vrf) and chosen.get("valid_from") and chosen["valid_from"] > vrf:
        problems.append(Issue(r["row"], "Методика поверки", ERROR, "методика",
                              f"«{doc}» вводится только с {chosen['valid_from']}, "
                              f"а поверка — {vrf}",
                              "на дату поверки эта редакция ещё не действовала"))

    if edition_in and edition_card and edition_in != edition_card:
        problems.append(Issue(r["row"], "Методика поверки", WARNING, "методика",
                              f"указана редакция изм. №{edition_in}, а в карточке — "
                              f"№{edition_card} ({label(chosen)})",
                              "проверьте, какая редакция действовала на дату поверки"))

    if chosen.get("valid_to") and chosen["valid_to"] < vrf:
        newer = [m for m in meth
                 if m.get("valid_from") and m["valid_from"] >= (chosen.get("valid_to") or "")]
        hint = (f"актуальная: {label(newer[0])}" if newer
                else "проверьте, нет ли новой редакции методики")
        problems.append(Issue(r["row"], "Методика поверки", WARNING, "методика",
                              f"«{doc}» действовала до {chosen['valid_to']} — "
                              f"на дату поверки ({vrf}) уже неактуальна",
                              hint))

    return problems


def rule_modification(r: dict, ctx: Context) -> list[Issue]:
    out: list[Issue] = []
    card = ctx.types.get((r.get("ot") or "").strip())
    mod = (r.get("modification") or "").strip()
    if not card or not mod:
        return out
    known = [x for x in (card.get("mods") or []) + (card.get("aliases") or []) if x]
    if not known:
        return out
    if any(norm_text(k) == norm_text(mod) for k in known):
        return out
    close = sorted(known, key=lambda k: levenshtein(mod, k))[:3]
    if close and levenshtein(mod, close[0]) <= 2:
        return [Issue(r["row"], "Модификация", WARNING, "модификация",
                      f"«{mod}» не найдена, похоже на «{close[0]}»",
                      "возможна опечатка или другое написание")]
    return [Issue(r["row"], "Модификация", WARNING, "модификация",
                  f"«{mod}» отсутствует в справочнике модификаций типа",
                  f"известные: {', '.join(known[:8])}")]


def rule_dates(r: dict, ctx: Context) -> list[Issue]:
    out: list[Issue] = []
    vrf = r.get("vrf_date")
    if not vrf:
        return out
    if ctx.today and vrf > ctx.today:
        out.append(Issue(r["row"], "Дата поверки", ERROR, "дата",
                         f"дата поверки в будущем ({vrf})"))
    if r.get("valid_date") and r["valid_date"] <= vrf:
        out.append(Issue(r["row"], "Действительно до", ERROR, "дата",
                         f"«действительно до» ({r['valid_date']}) не позже даты поверки"))
    return out


def rule_duplicates(r: dict, ctx: Context) -> list[Issue]:
    key = ((r.get("ot") or "").strip(),
           norm_number(r.get("mi_number") or r.get("inventory_number") or ""))
    if not key[0] or not key[1]:
        return []
    rows = ctx.batch_index.get(key, [])
    if len(rows) > 1 and r["row"] == rows[0]:
        return [Issue(r["row"], "Заводской номер", WARNING, "дубли",
                      f"одно СИ встречается в пачке {len(rows)} раза "
                      f"(строки {', '.join(map(str, rows))})",
                      "вторая запись перезапишет первую при публикации")]
    return []


def rule_dragfill(r: dict, ctx: Context) -> list[Issue]:
    """Эвристика «протяжки»: в пачке есть ОТ, отличающийся на 1, и его нет в реестре."""
    ot = (r.get("ot") or "").strip()
    if not re.match(r"^\d+-\d{2}$", ot):
        return []
    base, year = ot.rsplit("-", 1)
    if not base.isdigit():
        return []
    batch_ots = {o for (o, _mi) in ctx.batch_index}
    for delta in (+1, -1):
        neighbour = f"{int(base) + delta:0{len(base)}d}-{year}"
        if neighbour in batch_ots and neighbour not in ctx.types:
            return [Issue(r["row"], "ОТ", WARNING, "похоже на протяжку",
                          f"в пачке есть ОТ {ot} и {neighbour} (отличаются на 1), "
                          f"тип {neighbour} в реестре отсутствует",
                          "проверьте, не «протянули» ли ячейку с ОТ")]
    return []


def rule_conditions(r: dict, ctx: Context) -> list[Issue]:
    """Условия среды строки против листа «Ввод» (условия по датам)."""
    out: list[Issue] = []
    if not ctx.conditions_by_date:
        return out
    vrf = r.get("vrf_date")
    if not vrf or vrf not in ctx.conditions_by_date:
        return out
    exp_t, exp_p, exp_h = ctx.conditions_by_date[vrf]
    for key, col, exp in (("temperature", "Температура", exp_t),
                          ("pressure", "Давление", exp_p),
                          ("humidity", "Влажность", exp_h)):
        got = norm_condition(r.get(key))
        if got and exp and got != exp:
            out.append(Issue(r["row"], col, WARNING, "условия среды",
                             f"указано {got}, а на {vrf} в листе «Ввод» — {exp}",
                             "условия вводятся один раз на дату"))
    return out


RULES = [rule_required, rule_ot, rule_mpi, rule_reverify, rule_method,
         rule_modification, rule_dates, rule_duplicates, rule_dragfill, rule_conditions]

PROFILES: dict[str, tuple] = {
    # Методика добавлена в базовый профиль: смена редакции в описании типа — тот самый
    # случай, когда старая методика уходит в АРШИН без предупреждения.
    "mvp": (rule_ot, rule_mpi, rule_method),
    "full": tuple(RULES),
}


# ------------------------------------------------ проверки уровня файла
TYPE_WORDS = [
    "газоанализатор", "датчик", "давлени", "манометр", "температур", "термометр",
    "уровнемер", "тягонапоромер", "напоромер", "контроллер", "расходомер", "вибро",
    "вычислител", "влагомер", "эри", "агзу", "калибровк", "плотномер",
]


def check_filename(name: str, records: list[dict], titles: dict[str, str]) -> list[Issue]:
    """Сверка имени файла с содержимым: количество «(N шт.)» и тип СИ."""
    out: list[Issue] = []
    low = name.lower()
    m = re.search(r"(\d+)\s*шт", low)
    if m:
        declared, actual = int(m.group(1)), len(records)
        if declared != actual:
            out.append(Issue(0, "(файл)", ERROR, "имя файла",
                             f"в имени указано {declared} шт., а в файле {actual} записей",
                             "проверьте, что собран весь файл и выбран верный шаблон"))
    words = [w for w in TYPE_WORDS if w in low]
    if words:
        file_titles = " ".join(titles.get((r.get("ot") or "").strip(), "")
                               for r in records).lower()
        file_titles += " " + " ".join(str(r.get("mitype_title") or "") for r in records).lower()
        if file_titles.strip() and not any(w in file_titles for w in words):
            shown = sorted({titles.get((r.get("ot") or "").strip(), "") for r in records} - {""})
            out.append(Issue(0, "(файл)", WARNING, "имя файла",
                             f"в имени «{', '.join(words)}», а в файле: "
                             f"{'; '.join(t[:40] for t in shown[:3]) or 'типы не определены'}",
                             "возможно, файл собран не из той пачки"))
    return out


def check_ciphers(records: list[dict], allowed: set[str]) -> list[Issue]:
    """Не даём принять за свою пачку данные другой организации (шифр клейма)."""
    if not allowed:
        return []
    found: dict[str, int] = {}
    for r in records:
        cipher = (r.get("sign_cipher") or "").strip().upper()
        if cipher:
            found[cipher] = found.get(cipher, 0) + 1
    foreign = {c: n for c, n in found.items() if c not in allowed}
    if not foreign:
        return []
    if len(foreign) == len(found):
        return [Issue(0, "(файл)", ERROR, "чужой файл",
                      f"шифр клейма {', '.join(sorted(foreign))} — это данные другой "
                      f"организации (наш шифр: {', '.join(sorted(allowed))})",
                      "такую пачку в АРШИН загружать нельзя: это чужие поверки")]
    out: list[Issue] = []
    for r in records:
        cipher = (r.get("sign_cipher") or "").strip().upper()
        if cipher in foreign:
            out.append(Issue(r["row"], "Шифр клейма", WARNING, "чужой файл",
                             f"шифр {cipher} — не наш ({', '.join(sorted(allowed))})",
                             "проверьте, не попала ли в пачку чужая строка"))
    return out[:50]


def run(records: list[dict], ctx: Context) -> list[Issue]:
    """Прогнать правила профиля по записям."""
    ctx.batch_index = {}
    for r in records:
        key = ((r.get("ot") or "").strip(),
               norm_number(r.get("mi_number") or r.get("inventory_number") or ""))
        ctx.batch_index.setdefault(key, []).append(r["row"])
    issues: list[Issue] = []
    for r in records:
        for rule in PROFILES.get(ctx.profile, PROFILES["full"]):
            try:
                issues.extend(rule(r, ctx) or [])
            except Exception as exc:  # noqa: BLE001
                issues.append(Issue(r["row"], "", ERROR, "сбой правила",
                                    f"{rule.__name__}: {exc}"))
    return issues
