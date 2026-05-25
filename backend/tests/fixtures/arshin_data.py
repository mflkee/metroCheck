"""Mock ARSHIN data fixtures in real API format."""

from datetime import date
from typing import Any

SAMPLE_CALIBRATIONS_VRI = [
    {
        "vri_id": "1-419280775",
        "org_title": 'ООО "МКАИР"',
        "mit_number": "25913-08",
        "mit_title": "Манометры показывающие",
        "mit_notation": "ТМ, ТВ, ТМВ и ТМТБ",
        "mi_modification": "ТМ6",
        "mi_number": "С2065928",
        "verification_date": "26.02.2025",
        "valid_date": "25.02.2027",
        "result_docnum": "С-ЕЖБ/26-02-2025/419280775",
        "applicability": True,
    },
    {
        "vri_id": "1-419280776",
        "org_title": 'ООО "МКАИР"',
        "mit_number": "55450-13",
        "mit_title": "Газоанализаторы оптические",
        "mit_notation": "СГОЭС-М11",
        "mi_modification": "СГОЭС-М11",
        "mi_number": "2411",
        "verification_date": "02.12.2025",
        "valid_date": "01.12.2027",
        "result_docnum": "12/081/25",
        "applicability": True,
    },
    {
        "vri_id": "1-419280777",
        "org_title": 'ООО "МКАИР"',
        "mit_number": "56503-14",
        "mit_title": "Уровнемеры поплавковые",
        "mit_notation": "ДУУ10",
        "mi_modification": "ДУУ10",
        "mi_number": "1816",
        "verification_date": "02.12.2025",
        "valid_date": "01.12.2027",
        "result_docnum": "12/087/25",
        "applicability": True,
    },
    {
        "vri_id": "1-419280778",
        "org_title": 'ООО "МКАИР"',
        "mit_number": "53211-13",
        "mit_title": "Термопреобразователи сопротивления",
        "mit_notation": "Rosemount 0065",
        "mi_modification": "Rosemount 0065",
        "mi_number": "2330280",
        "verification_date": "01.12.2025",
        "valid_date": "30.11.2027",
        "result_docnum": "12/042/25",
        "applicability": True,
    },
]

SAMPLE_LK_DETAIL = {
    "id": 423091570,
    "verificationDate": "2025-12-02",
    "mitypeNumber": "55450-13",
    "factoryNum": "2411",
    "count": 1,
    "documentTitle": "12/081/25",
    "applicability": True,
    "status": "PUBLISHED",
    "lastChanged": "2025-12-02T08:16:33.5",
    "author": "Чупин А.А.",
    "lastAuthor": "Система",
    "owner": 'ООО "ГАЗПРОМНЕФТЬ-ЯМАЛ"',
    "globalId": 419280776,
}

SAMPLE_LK_DATA2 = {
    "id": 423091572,
    "orgId": 2163,
    "vcs": "ЕЖБ",
    "owner": 'ООО "ГАЗПРОМНЕФТЬ-ЯМАЛ"',
    "verificationDate": "2025-12-02",
    "etaIndicator": False,
    "validFor": "2027-12-01",
    "applicability": True,
    "docTitle": "МП-242-1561-2013",
    "certificateNum": "12/081/25",
    "signPass": True,
    "signMi": True,
    "verifierName": "Чупин А.А.",
    "additionalInfo": "(0 - 100)%",
    "status": "PUBLISHED",
    "globalId": 419280776,
    "lastChanged": "2025-12-02T08:16:33.422",
    "lastAuthor": "Система",
    "calibrationIndicator": False,
    "conditionsTemperature": "20,1°С",
    "conditionsPressure": "100,9 кПа",
    "conditionsHymidity": "30,0",
    "briefIndicator": False,
    "vriType": "PERIODICAL",
    "means": {
        "mietas": [
            {"id": 544183286, "number": "01670-25"},
            {"id": 544183285, "number": "01668-25"},
        ]
    },
    "typeType": "INSTRUMENT_MEASURING_TYPE",
    "mitypeNumber": "55450-13",
    "modification": "СГОЭС-М11",
    "factoryNum": "2411",
    "year": "2014",
}

SAMPLE_PROTOCOL_EXTRACTIONS = [
    {
        "protocol_number": "12/081/25",
        "device_name": "Газоанализатор оптический СГОЭС - М11",
        "serial_number": "2411",
        "mit_number": "55450-13",
        "manufacture_year": 2014,
        "owner": 'ООО "ГАЗПРОМНЕФТЬ-ЯМАЛ"',
        "verification_date": date(2025, 12, 2),
        "verifier": "Чупин А.А.",
        "temperature": 20.1,
        "humidity": 30.0,
        "pressure": 100.9,
        "pressure_units": "кПа",
        "result": "годен",
        "verification_method": "Газоанализаторы СГОЭС-М11. Методика поверки",
    },
    {
        "protocol_number": "12/087/25",
        "device_name": "Уровнемеры поплавковые ДУУ10",
        "serial_number": "1816",
        "mit_number": "56503-14",
        "manufacture_year": 2021,
        "owner": 'ООО "ГАЗПРОМНЕФТЬ-ЯМАЛ"',
        "verification_date": date(2025, 12, 2),
        "verifier": "Чупин А.А.",
        "temperature": 20.1,
        "humidity": 30.0,
        "pressure": 100.9,
        "pressure_units": "kPa",
        "result": "suitable",
        "verification_method": "УНКР.407631.005 МП",
    },
    {
        "protocol_number": "12/042/25",
        "device_name": "Термопреобразователь сопротивления Rosemount 0065",
        "serial_number": "2330280",
        "mit_number": "53211-13",
        "manufacture_year": 2016,
        "owner": 'ООО "ГАЗПРОМНЕФТЬ-ЯМАЛ"',
        "verification_date": date(2025, 12, 1),
        "verifier": "Чупин А.А.",
        "temperature": 24.3,
        "humidity": 34.0,
        "pressure": 100.4,
        "pressure_units": "kPa",
        "result": "suitable",
        "verification_method": "ГОСТ 8.461-2009",
    },
]


def build_calibration_from_vri(vri_item: dict[str, Any], year: int, month: int) -> dict[str, Any]:
    """Build a Calibration model dict from a VRI API item."""
    from datetime import datetime

    def parse_date(value: str | None) -> date | None:
        if not value:
            return None
        for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
        return None

    return {
        "vri_id": vri_item["vri_id"],
        "org_title": vri_item.get("org_title", 'ООО "МКАИР"'),
        "mit_number": vri_item.get("mit_number"),
        "mit_title": vri_item.get("mit_title"),
        "mi_number": (vri_item.get("mi_number") or "").strip(),
        "verification_date": parse_date(vri_item.get("verification_date")),
        "valid_date": parse_date(vri_item.get("valid_date")),
        "result_docnum": vri_item.get("result_docnum"),
        "result": "suitable" if vri_item.get("applicability") else "unsuitable",
        "year": year,
        "month": month,
    }
