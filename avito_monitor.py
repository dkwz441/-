from __future__ import annotations

import json
import os
import queue
import random
import re
import shutil
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import tkinter as tk
from tkinter import messagebox, ttk

from playwright.sync_api import BrowserContext, Page, sync_playwright


APP_DIR = Path(__file__).resolve().parent
PROFILE_DIR = APP_DIR / ".avito-browser-profile"
SEEN_FILE = APP_DIR / ".avito-seen.json"
AUTH_STATE_FILE = APP_DIR / ".avito-auth-state.json"
MIN_INTERVAL_SECONDS = 60
CHALLENGE_WAIT_SECONDS = 600
CARD_SELECTOR = '[data-marker="item"], [data-item-id]'

CITIES = {
    "Вся Россия": "rossiya",
    "Москва": "moskva",
    "Санкт-Петербург": "sankt-peterburg",
    "Новосибирск": "novosibirsk",
    "Екатеринбург": "ekaterinburg",
    "Казань": "kazan",
    "Нижний Новгород": "nizhniy_novgorod",
    "Краснодар": "krasnodar",
    "Челябинск": "chelyabinsk",
    "Самара": "samara",
    "Уфа": "ufa",
    "Ростов-на-Дону": "rostov-na-donu",
    "Омск": "omsk",
    "Красноярск": "krasnoyarsk",
    "Воронеж": "voronezh",
    "Пермь": "perm",
    "Волгоград": "volgograd",
    "Тюмень": "tyumen",
    "Саратов": "saratov",
    "Тула": "tula",
}

CATEGORIES = {
    "Все категории": "all",
    "Электроника": "elektronika",
    "Бытовая техника": "bytovaya_tehnika",
    "Для дома и дачи": "dlya_doma_i_dachi",
    "Личные вещи": "lichnye_veschi",
    "Транспорт": "transport",
    "Запчасти и аксессуары": "zapchasti_i_aksessuary",
    "Хобби и отдых": "hobbi_i_otdyh",
    "Животные": "zhivotnye",
    "Недвижимость": "nedvizhimost",
    "Работа": "rabota",
    "Услуги": "uslugi",
    "Готовый бизнес и оборудование": "gotoviy_biznes_i_oborudovanie",
}

PRODUCTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Другой товар": ("", ()),
    "Оперативная память": (
        "оперативная память",
        (
            "ADATA", "AMD", "Apacer", "Asgard", "Acer Predator", "Biwin", "Corsair", "Crucial",
            "Digma", "Exegate", "Foxline", "G.Skill", "GeIL", "Gigabyte", "Gloway", "Goodram",
            "Hiksemi", "Hynix", "KingBank", "Kingmax", "Kingston", "KLEVV", "Lexar", "Micron",
            "Mushkin", "Netac", "OLOy", "Patriot", "PNY", "Qumo", "Samsung", "Silicon Power",
            "SK hynix", "TeamGroup", "Thermaltake", "Transcend", "V-Color", "Walram", "XPG",
            "Juhor", "Zeppelin",
        ),
    ),
    "Процессор": ("процессор", ("AMD", "Intel")),
    "Видеокарта": (
        "видеокарта",
        (
            "AFOX", "AMD", "ASRock", "ASUS", "Biostar", "Colorful", "Dell", "EVGA", "Gainward",
            "Galax", "Gigabyte", "HP", "Inno3D", "Intel", "KFA2", "Leadtek", "Lenovo", "Manli",
            "Maxsun", "MSI", "NVIDIA", "Palit", "PNY", "PowerColor", "Sapphire", "Sinotex Ninja",
            "Sparkle", "XFX", "Yeston", "Zotac",
        ),
    ),
    "Материнская плата": (
        "материнская плата",
        (
            "AFOX", "ASRock", "ASUS", "Biostar", "Colorful", "ECS", "EVGA", "Foxconn", "Gigabyte",
            "HUANANZHI", "JGINYUE", "Machinist", "Maxsun", "MSI", "NZXT", "Supermicro", "X99",
        ),
    ),
    "SSD": (
        "SSD",
        (
            "ADATA", "Apacer", "Biwin", "Crucial", "Digma", "Fanxiang", "Goodram", "Hiksemi",
            "Intel", "Kingston", "Kioxia", "Lexar", "Micron", "Netac", "OCZ", "Patriot", "PNY",
            "Samsung", "SanDisk", "Seagate", "Silicon Power", "SK hynix", "Smartbuy", "TeamGroup",
            "Transcend", "Western Digital", "XPG", "KingSpec",
        ),
    ),
    "Жёсткий диск": (
        "жесткий диск HDD",
        ("HGST", "Hitachi", "Samsung", "Seagate", "Toshiba", "Western Digital"),
    ),
    "Блок питания": (
        "блок питания для компьютера",
        (
            "AeroCool", "ASUS", "be quiet!", "Chieftec", "Cooler Master", "Corsair", "Cougar",
            "DeepCool", "Enermax", "EVGA", "ExeGate", "FSP", "Fractal Design", "Gigabyte",
            "MSI", "Montech", "NZXT", "Phanteks", "Seasonic", "SilverStone", "Super Flower",
            "Thermaltake", "Xilence", "Zalman",
        ),
    ),
    "Охлаждение": (
        "кулер охлаждение процессора",
        (
            "Alphacool", "Arctic", "ASUS", "be quiet!", "Cooler Master", "Corsair", "Cougar",
            "DeepCool", "EKWB", "Enermax", "ID-Cooling", "Jonsbo", "Lian Li", "Noctua", "NZXT",
            "PCCooler", "Scythe", "Thermalright", "Thermaltake", "Zalman",
        ),
    ),
    "Корпус компьютера": (
        "корпус для компьютера",
        (
            "AeroCool", "Antec", "ASUS", "be quiet!", "Cooler Master", "Corsair", "Cougar",
            "DeepCool", "Fractal Design", "Jonsbo", "Lian Li", "Montech", "NZXT", "Phanteks",
            "SilverStone", "Thermaltake", "Zalman",
        ),
    ),
    "Вентилятор для корпуса": (
        "вентилятор для корпуса",
        ("AeroCool", "Arctic", "be quiet!", "Cooler Master", "Corsair", "Cougar", "DeepCool", "ID-Cooling", "Lian Li", "Noctua", "NZXT", "Phanteks", "Scythe", "Thermalright", "Thermaltake", "Xilence", "Zalman"),
    ),
    "Звуковая карта": (
        "звуковая карта",
        ("ASUS", "Behringer", "Creative", "ESI", "Focusrite", "M-Audio", "PreSonus", "Steinberg", "Tascam", "Universal Audio"),
    ),
    "Сетевая карта": (
        "сетевая карта",
        ("ASUS", "Broadcom", "D-Link", "Intel", "Killer", "Mellanox", "Mercusys", "Realtek", "TP-Link", "Ugreen", "Zyxel"),
    ),
    "Плата расширения": (
        "контроллер плата расширения PCIe",
        ("ASUS", "Broadcom", "Espada", "HighPoint", "Intel", "LSI", "ORICO", "QNAP", "SilverStone", "StarTech", "Ugreen"),
    ),
    "Оптический привод": ("DVD Blu-ray привод", ("ASUS", "Hitachi-LG", "LG", "Lite-On", "NEC", "Optiarc", "Pioneer", "Samsung")),
    "Термопаста": ("термопаста", ("Arctic", "Cooler Master", "DeepCool", "Gelid", "Grizzly", "ID-Cooling", "Noctua", "Thermalright", "Zalman")),
    "Кабели и переходники": ("кабель переходник для компьютера", ("Baseus", "Cablexpert", "D-Link", "Espada", "ORICO", "Rexant", "UGREEN", "Vention")),
    "Комплектующие для ноутбука": ("комплектующие для ноутбука", ("Acer", "Apple", "ASUS", "Dell", "HP", "Huawei", "Lenovo", "MSI", "Samsung", "Xiaomi")),
    "Серверные комплектующие": ("серверные комплектующие", ("Broadcom", "Cisco", "Dell", "Fujitsu", "HPE", "Huawei", "IBM", "Intel", "Lenovo", "LSI", "Mellanox", "Micron", "Samsung", "Seagate", "Supermicro", "Western Digital")),
    "Ноутбук": (
        "ноутбук",
        (
            "Acer", "Apple", "ASUS", "Chuwi", "Dell", "DEXP", "Dream Machines", "Gigabyte",
            "Honor", "HP", "Huawei", "Lenovo", "Maibenben", "MSI", "Razer", "Samsung", "Thunderobot",
            "Xiaomi",
        ),
    ),
    "Монитор": (
        "монитор",
        (
            "Acer", "AOC", "ASUS", "BenQ", "Dell", "Gigabyte", "HP", "Huawei", "Iiyama", "LG",
            "MSI", "Philips", "Samsung", "ViewSonic", "Xiaomi",
        ),
    ),
    "Смартфон": ("смартфон", ("Apple", "ASUS", "Google", "Honor", "Huawei", "Infinix", "Motorola", "Nokia", "Nothing", "OnePlus", "OPPO", "Realme", "Samsung", "Sony", "Tecno", "Vivo", "Xiaomi", "ZTE")),
    "Планшет": ("планшет", ("Apple", "Blackview", "Honor", "Huawei", "Lenovo", "Microsoft", "Samsung", "Teclast", "Xiaomi")),
    "Игровая консоль": ("игровая приставка", ("Microsoft Xbox", "Nintendo", "Sony PlayStation", "Valve Steam Deck")),
    "Телевизор": ("телевизор", ("BBK", "Haier", "Hisense", "LG", "Philips", "Samsung", "Sony", "TCL", "Xiaomi", "Яндекс")),
    "Наушники": ("наушники", ("Apple", "Audio-Technica", "Beyerdynamic", "Bose", "HyperX", "JBL", "Marshall", "Razer", "Sennheiser", "Sony", "SteelSeries", "Xiaomi")),
}

COMPONENT_NAMES = (
    "Оперативная память",
    "Процессор",
    "Видеокарта",
    "Материнская плата",
    "SSD",
    "Жёсткий диск",
    "Блок питания",
    "Охлаждение",
    "Вентилятор для корпуса",
    "Корпус компьютера",
    "Звуковая карта",
    "Сетевая карта",
    "Плата расширения",
    "Оптический привод",
    "Термопаста",
    "Кабели и переходники",
    "Комплектующие для ноутбука",
    "Серверные комплектующие",
    "Другой товар",
)

PRODUCT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Оперативная память": ("оператив", "озу", " ram", "ddr", "dimm", "sodimm"),
    "Процессор": ("процессор", " cpu", "ryzen", "xeon", "core i", "athlon", "celeron", "pentium", "epyc", "threadripper"),
    "Видеокарта": ("видеокарт", " gpu", "geforce", "radeon", " rtx", " gtx", "quadro", "intel arc"),
    "Материнская плата": ("материн", "motherboard", "mainboard"),
    "SSD": (" ssd", "ssd ", "nvme", "m.2", "твердотель"),
    "Жёсткий диск": ("жестк", "жёстк", " hdd", "hdd "),
    "Блок питания": ("блок питания", " psu", "ватт", " watt", "w gold", "w bronze"),
    "Охлаждение": ("кулер", "охлажден", "водян", "радиатор", " aio"),
    "Вентилятор для корпуса": ("вентилятор", "вертушк", " fan"),
    "Корпус компьютера": ("корпус", "case ", "computer case"),
    "Звуковая карта": ("звуков", "audio interface", "цап", " dac"),
    "Сетевая карта": ("сетев", "ethernet", " wi-fi", "wifi", "lan карт"),
    "Плата расширения": ("контроллер", "плата расширения", "pcie", "pci-e"),
    "Оптический привод": ("dvd", "blu-ray", "bluray", "оптический привод"),
    "Термопаста": ("термопаст", "thermal paste", "термоинтерфейс"),
    "Кабели и переходники": ("кабель", "переходник", "адаптер"),
    "Комплектующие для ноутбука": ("для ноутбука", "ноутбуч", "laptop"),
    "Серверные комплектующие": ("сервер", "server", "sas", "raid", "ecc reg"),
}

MANUFACTURER_ALIASES: dict[str, tuple[str, ...]] = {
    "AMD": ("amd", "ryzen", "radeon", "athlon", "epyc", "threadripper"),
    "Intel": ("intel", "core i", "xeon", "pentium", "celeron", "intel arc"),
    "NVIDIA": ("nvidia", "geforce", "rtx", "gtx", "quadro"),
    "Western Digital": ("western digital", " wd"),
    "SK hynix": ("sk hynix", "hynix"),
    "Hynix": ("hynix",),
    "be quiet!": ("be quiet",),
    "Microsoft Xbox": ("xbox",),
    "Sony PlayStation": ("playstation", "ps4", "ps5"),
}

IRRELEVANT_PHRASES = (
    "куплю ",
    "ищу ",
    "коробка от",
    "упаковка от",
    "муляж",
    "ремонт видеокарт",
    "ремонт компьютеров",
    "услуги ремонта",
)

SMART_PRODUCT_ALIASES: dict[str, tuple[str, ...]] = {
    "Оперативная память": ("оперативная память", "оперативка", "озу", "ram"),
    "Процессор": ("процессор", "проц", "cpu"),
    "Видеокарта": ("видеокарта", "видюха", "видео карта", "gpu"),
    "Материнская плата": ("материнская плата", "материнка", "мать", "motherboard"),
    "SSD": ("ssd", "ссд", "nvme"),
    "Жёсткий диск": ("жесткий диск", "жёсткий диск", "hdd", "винчестер"),
    "Блок питания": ("блок питания", "бп", "psu"),
    "Охлаждение": ("охлаждение", "кулер", "водянка", "сжо", "aio"),
    "Вентилятор для корпуса": ("корпусной вентилятор", "вентилятор", "вертушка"),
    "Корпус компьютера": ("корпус компьютера", "корпус пк", "computer case"),
    "Звуковая карта": ("звуковая карта", "цап", "dac"),
    "Сетевая карта": ("сетевая карта", "wifi карта", "wi-fi карта"),
    "Плата расширения": ("плата расширения", "pcie контроллер", "pci-e контроллер"),
    "Термопаста": ("термопаста", "термоинтерфейс"),
}


@dataclass(frozen=True)
class Listing:
    listing_id: str
    title: str
    price: int | None
    url: str

    @property
    def display_price(self) -> str:
        return f"{self.price:,} ₽".replace(",", " ") if self.price is not None else "цена не указана"


@dataclass(frozen=True)
class AutomationSettings:
    send_message: bool
    message_text: str
    open_checkout: bool
    confirm_purchase: bool
    max_actions: int


def build_search_url(category_url: str, query: str, max_price: int | None) -> str:
    raw_url = category_url.strip() or "https://www.avito.ru/all"
    if not raw_url.startswith(("https://", "http://")):
        raw_url = "https://www.avito.ru/" + raw_url.lstrip("/")

    parsed = urlparse(raw_url)
    if parsed.hostname not in {"avito.ru", "www.avito.ru"}:
        raise ValueError("Ссылка категории должна вести на avito.ru")

    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query.strip():
        params["q"] = query.strip()
    else:
        params.pop("q", None)
    if max_price is not None:
        params["pmax"] = str(max_price)
    else:
        params.pop("pmax", None)
    params["s"] = "104"  # сначала новые
    return urlunparse(parsed._replace(query=urlencode(params)))


def price_from_text(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else None


def normalize_search_text(value: str) -> str:
    text = value.casefold().replace("ё", "е").replace("×", "x").replace("х", "x").replace("*", "x")
    text = re.sub(r"(\d+)\s*x\s*(\d+)", r"\1x\2", text)
    text = re.sub(r"(\d+)\s*(?:гб|gb|gbyte|гигабайт(?:а|ов)?)\b", r"\1gb", text)
    text = re.sub(r"(\d+)\s*(?:тб|tb|tbyte|терабайт(?:а|ов)?)\b", r"\1tb", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_smart_query(value: str) -> tuple[str, str, str]:
    normalized = normalize_search_text(value)
    detected_product = "Другой товар"
    matched_alias = ""
    for product, aliases in SMART_PRODUCT_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if normalize_search_text(alias) in normalized:
                detected_product = product
                matched_alias = normalize_search_text(alias)
                break
        if matched_alias:
            break

    detected_manufacturer = "Любой производитель"
    if detected_product in PRODUCTS:
        for maker in sorted(PRODUCTS[detected_product][1], key=len, reverse=True):
            aliases = MANUFACTURER_ALIASES.get(maker, (maker.casefold(),))
            if any(normalize_search_text(alias) in normalized for alias in aliases):
                detected_manufacturer = maker
                break

    remaining = normalized
    if matched_alias:
        remaining = remaining.replace(matched_alias, " ", 1)
    if detected_manufacturer != "Любой производитель":
        aliases = MANUFACTURER_ALIASES.get(detected_manufacturer, (detected_manufacturer.casefold(),))
        for alias in sorted(aliases, key=len, reverse=True):
            normalized_alias = normalize_search_text(alias)
            if normalized_alias in remaining:
                remaining = remaining.replace(normalized_alias, " ", 1)
                break
    remaining = re.sub(r"\s+", " ", remaining).strip(" ,;-")
    return detected_product, detected_manufacturer, remaining


def required_specs(value: str) -> tuple[str, ...]:
    normalized = normalize_search_text(value)
    specs = re.findall(r"\b\d+x\d+(?:gb)?\b|\b\d+(?:gb|tb)\b|\bddr\d\b|\b(?:rtx|gtx|rx)\s*\d+\w*\b|\b\d{3,4}w\b", normalized)
    return tuple(spec.replace(" ", "") for spec in specs)


def listing_is_relevant(
    listing: Listing,
    product_name: str,
    manufacturer: str,
    extra_query: str,
) -> bool:
    title = normalize_search_text(listing.title)
    if any(normalize_search_text(phrase) in title for phrase in IRRELEVANT_PHRASES):
        return False

    if product_name != "Другой товар":
        keywords = tuple(normalize_search_text(word) for word in PRODUCT_KEYWORDS.get(product_name, ()))
        if keywords and not any(word in f" {title}" for word in keywords):
            return False

    if manufacturer and manufacturer != "Любой производитель":
        aliases = MANUFACTURER_ALIASES.get(manufacturer, (manufacturer.casefold(),))
        if not any(normalize_search_text(alias) in f" {title}" for alias in aliases):
            return False

    compact_title = title.replace(" ", "")
    if any(spec not in compact_title for spec in required_specs(extra_query)):
        return False
    return True


def page_url(search_url: str, page_number: int) -> str:
    parsed = urlparse(search_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if page_number > 1:
        params["p"] = str(page_number)
    else:
        params.pop("p", None)
    return urlunparse(parsed._replace(query=urlencode(params)))


def seen_file(profile_slot: int = 1) -> Path:
    return APP_DIR / f".avito-seen-{profile_slot}.json"


def load_seen(profile_slot: int = 1) -> set[str]:
    try:
        data = json.loads(seen_file(profile_slot).read_text(encoding="utf-8"))
        return {str(item) for item in data}
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        return set()


def save_seen(seen: set[str], profile_slot: int = 1) -> None:
    # Ограничиваем файл, чтобы многомесячный мониторинг не раздувал его бесконечно.
    seen_file(profile_slot).write_text(
        json.dumps(sorted(seen)[-20_000:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_listings(page: Page) -> list[Listing]:
    cards = page.locator(CARD_SELECTOR)
    raw_items = cards.evaluate_all(
        """
        cards => cards.map(card => {
          const link = card.querySelector(
            'a[data-marker="item-title"], [data-marker="item-title"] a, a[itemprop="url"], h3 a, h2 a'
          );
          const titleNode = card.querySelector(
            '[data-marker="item-title"], [itemprop="name"], h3, h2'
          );
          const priceNode = card.querySelector(
            'meta[itemprop="price"], [itemprop="price"], [data-marker="item-price"], [class*="price"]'
          );
          const href = link ? link.href : '';
          return {
            id: card.getAttribute('data-item-id') || href,
            title: titleNode ? titleNode.textContent.trim() : (link ? link.textContent.trim() : ''),
            price: priceNode ? (priceNode.getAttribute('content') || priceNode.textContent) : '',
            url: href
          };
        }).filter(item => item.id && item.title && item.url)
        """
    )
    listings: list[Listing] = []
    found_ids: set[str] = set()
    for item in raw_items:
        listing_id = str(item["id"])
        if listing_id in found_ids:
            continue
        found_ids.add(listing_id)
        listings.append(
            Listing(
                listing_id=listing_id,
                title=str(item["title"]),
                price=price_from_text(str(item.get("price", ""))),
                url=str(item["url"]),
            )
        )
    return listings


def page_has_challenge(page: Page) -> bool:
    signals = (
        "captcha",
        "доступ временно ограничен",
        "подтвердите, что вы не робот",
        "пройдите проверку",
        "проверка безопасности",
        "проверяем ваш браузер",
        "проверка ip",
        "это займет несколько секунд",
        "checking your browser",
        "security check",
    )
    try:
        haystack = f"{page.title()} {page.url} {page.locator('body').inner_text(timeout=3_000)}".lower()
    except Exception:
        haystack = f"{page.title()} {page.url}".lower()
    return any(signal in haystack for signal in signals)


def wait_for_manual_challenge(
    page: Page,
    stop_event: threading.Event,
    emit: Callable[[str, object], None],
) -> bool:
    emit("challenge", None)
    deadline = time.monotonic() + CHALLENGE_WAIT_SECONDS
    challenge_cleared_at: float | None = None
    reloads = 0
    while time.monotonic() < deadline and not stop_event.is_set():
        if page.locator(CARD_SELECTOR).count() > 0 and not page_has_challenge(page):
            emit("status", "Проверка пройдена, продолжаю мониторинг…")
            return True
        if page_has_challenge(page):
            challenge_cleared_at = None
        else:
            if challenge_cleared_at is None:
                challenge_cleared_at = time.monotonic()
            elif time.monotonic() - challenge_cleared_at >= 1 and reloads < 4:
                reloads += 1
                emit("status", f"Проверка завершилась, перезагружаю Avito ({reloads}/4)…")
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                challenge_cleared_at = time.monotonic()
        stop_event.wait(2)
    return False


def system_browser(preferred: str = "Chromium") -> str | None:
    if preferred == "Brave":
        candidates = [
            shutil.which("brave-browser"),
            shutil.which("brave"),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware/Brave-Browser/Application/brave.exe"),
            str(Path(os.environ.get("PROGRAMFILES", "")) / "BraveSoftware/Brave-Browser/Application/brave.exe"),
            str(Path(os.environ.get("PROGRAMFILES(X86)", "")) / "BraveSoftware/Brave-Browser/Application/brave.exe"),
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
    else:
        candidates = [
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
        ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def browser_profile_dir(browser_name: str, profile_slot: int) -> Path:
    profile_name = ".avito-brave-profile" if browser_name == "Brave" else ".avito-browser-profile"
    return APP_DIR / f"{profile_name}-{profile_slot}"


def save_auth_state(context: BrowserContext) -> None:
    context.storage_state(path=str(AUTH_STATE_FILE))


def restore_auth_state(context: BrowserContext) -> bool:
    try:
        state = json.loads(AUTH_STATE_FILE.read_text(encoding="utf-8"))
        cookies = state.get("cookies", [])
        if cookies:
            context.add_cookies(cookies)
        for origin_data in state.get("origins", []):
            origin = origin_data.get("origin")
            storage = origin_data.get("localStorage", [])
            if not origin or not storage:
                continue
            payload = json.dumps({"origin": origin, "items": storage}, ensure_ascii=True)
            script = f"""
            (() => {{
              const data = {payload};
              if (location.origin === data.origin) {{
                for (const item of data.items) localStorage.setItem(item.name, item.value);
              }}
            }})();
            """
            context.add_init_script(script=script)
        return bool(cookies)
    except (FileNotFoundError, OSError, json.JSONDecodeError, TypeError):
        return False


def is_avito_logged_in(page: Page) -> bool:
    try:
        url = page.url.casefold()
        body = normalize_search_text(page.locator("body").inner_text(timeout=3_000))
        username_controls = page.locator(
            '[data-marker="header/username-button"], [data-marker="header/profile"], '
            'a[href*="/profile/items"], a[href*="/profile/messenger"]'
        ).count()
        login_controls = page.locator(
            '[data-marker="header/login-button"], a[href*="/login"], button:has-text("Войти")'
        ).count()
    except Exception:
        return False
    logged_out_signals = (
        "войти или зарегистрироваться",
        "вход и регистрация",
        "войти в аккаунт",
        "продолжить с телефоном",
    )
    if "login" in url or any(signal in body for signal in logged_out_signals):
        return False
    if username_controls and not login_controls:
        return True
    logged_in_signals = (
        "мои объявления",
        "мои заказы",
        "настройки профиля",
        "управление профилем",
        "кошелек",
        "отзывы",
    )
    if "/profile" in url and any(signal in body for signal in logged_in_signals):
        return True
    try:
        cookie_names = {cookie["name"].casefold() for cookie in page.context.cookies("https://www.avito.ru")}
    except Exception:
        cookie_names = set()
    return "/profile" in url and "sessid" in cookie_names and not login_controls and len(body) > 100


def click_named_control(page: Page, names: tuple[str, ...]) -> bool:
    for name in names:
        pattern = re.compile(name, re.IGNORECASE)
        for role in ("button", "link"):
            control = page.get_by_role(role, name=pattern).first
            try:
                if control.count() and control.is_visible():
                    control.click(timeout=10_000)
                    return True
            except Exception:
                continue
    return False


def automate_listing(
    context: BrowserContext,
    listing: Listing,
    settings: AutomationSettings,
    emit: Callable[[str, object], None],
) -> None:
    page = context.new_page()
    page.goto(listing.url, wait_until="domcontentloaded", timeout=60_000)
    if page_has_challenge(page):
        page.bring_to_front()
        raise RuntimeError("Avito запросил ручную проверку в карточке объявления")

    if settings.send_message:
        if not click_named_control(page, (r"написать сообщение", r"написать продавцу", r"сообщение")):
            raise RuntimeError("не найдена кнопка сообщения продавцу")
        page.wait_for_timeout(1_000)
        editor = page.locator('textarea, [contenteditable="true"]').last
        if not editor.count() or not editor.is_visible():
            raise RuntimeError("не найдено поле сообщения; возможно, требуется вход")
        editor.fill(settings.message_text)
        if not click_named_control(page, (r"^отправить$", r"отправить сообщение")):
            raise RuntimeError("не найдена кнопка отправки сообщения")
        emit("automation", f"Сообщение отправлено: {listing.title}")
        page.wait_for_timeout(500)
        if settings.open_checkout:
            page.goto(listing.url, wait_until="domcontentloaded", timeout=60_000)

    if settings.open_checkout:
        if not click_named_control(
            page,
            (r"купить с доставкой", r"оформить доставку", r"забронировать", r"перейти к оформлению"),
        ):
            raise RuntimeError("у объявления нет кнопки покупки или бронирования")
        page.wait_for_timeout(2_000)
        checkout_page = context.pages[-1]
        checkout_page.bring_to_front()
        emit("automation", f"Оформление открыто: {listing.title}")

        if settings.confirm_purchase:
            if page_has_challenge(checkout_page):
                raise RuntimeError("перед оплатой требуется ручная проверка")
            if click_named_control(
                checkout_page,
                (r"^оплатить", r"^оформить заказ$", r"^подтвердить заказ$", r"^купить$"),
            ):
                emit("automation", f"Заказ подтверждён: {listing.title}")
            else:
                raise RuntimeError(
                    "не найдена финальная кнопка; проверь адрес, доставку и оплату в открытом окне"
                )
    else:
        page.close()


def load_results_page(
    page: Page,
    url: str,
    visible: bool,
    stop_event: threading.Event,
    emit: Callable[[str, object], None],
) -> list[Listing]:
    for attempt in range(1, 4):
        if attempt == 1:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        else:
            emit("status", f"Avito не загрузился, обновляю страницу ({attempt}/3)…")
            page.reload(wait_until="domcontentloaded", timeout=60_000)
        try:
            page.locator(CARD_SELECTOR).first.wait_for(timeout=20_000)
            return extract_listings(page)
        except Exception:
            if page_has_challenge(page):
                if not visible:
                    raise RuntimeError(
                        "Avito запросил проверку. Включи «Показывать браузер» и запусти монитор снова."
                    )
                if wait_for_manual_challenge(page, stop_event, emit):
                    return extract_listings(page)
                if stop_event.is_set():
                    return []
                raise RuntimeError("Проверка Avito не пройдена за 10 минут.")
            try:
                body = normalize_search_text(page.locator("body").inner_text(timeout=3_000))
            except Exception:
                body = ""
            if "ничего не найдено" in body or "объявлений не найдено" in body:
                return []
    return extract_listings(page)


class MonitorWorker:
    def __init__(self, emit: Callable[[str, object], None]) -> None:
        self.emit = emit
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(
        self,
        url: str,
        max_price: int | None,
        interval: int,
        max_pages: int,
        product_name: str,
        manufacturer: str,
        extra_query: str,
        smart_filter: bool,
        visible: bool,
        browser_name: str,
        profile_slot: int,
        automation: AutomationSettings,
    ) -> None:
        self.stop()
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            args=(
                url, max_price, interval, max_pages, product_name, manufacturer, extra_query,
                smart_filter, visible, browser_name, profile_slot, automation,
            ),
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _run(
        self,
        url: str,
        max_price: int | None,
        interval: int,
        max_pages: int,
        product_name: str,
        manufacturer: str,
        extra_query: str,
        smart_filter: bool,
        visible: bool,
        browser_name: str,
        profile_slot: int,
        automation: AutomationSettings,
    ) -> None:
        seen = load_seen(profile_slot)
        actions_done = 0
        first_scan = True
        try:
            with sync_playwright() as playwright:
                launch_options: dict[str, object] = {
                    "headless": not visible,
                    "locale": "ru-RU",
                    "viewport": {"width": 1280, "height": 900},
                }
                executable = system_browser(browser_name)
                if browser_name == "Brave" and not executable:
                    raise RuntimeError("Brave не найден. Установи Brave или выбери Chromium в настройках.")
                if executable:
                    launch_options["executable_path"] = executable
                profile_dir = browser_profile_dir(browser_name, profile_slot)
                context: BrowserContext = playwright.chromium.launch_persistent_context(
                    str(profile_dir),
                    **launch_options,
                )
                if restore_auth_state(context):
                    self.emit("status", "Сохранённая сессия Avito загружена")
                page = context.pages[0] if context.pages else context.new_page()
                while not self.stop_event.is_set():
                    items: list[Listing] = []
                    collected_ids: set[str] = set()
                    for page_number in range(1, max_pages + 1):
                        if self.stop_event.is_set():
                            break
                        self.emit("status", f"Проверяю страницу {page_number} из {max_pages}…")
                        page_items = load_results_page(
                            page,
                            page_url(url, page_number),
                            visible,
                            self.stop_event,
                            self.emit,
                        )
                        if not page_items:
                            break
                        for item in page_items:
                            if item.listing_id not in collected_ids:
                                collected_ids.add(item.listing_id)
                                items.append(item)
                        if page_number < max_pages and self.stop_event.wait(random.uniform(1.0, 2.5)):
                            break
                    if self.stop_event.is_set():
                        break
                    if not items:
                        self.emit("status", "Объявления не найдены; возможно, Avito изменил страницу или показал проверку.")
                    else:
                        matching = [
                            item
                            for item in items
                            if max_price is None or item.price is None or item.price <= max_price
                            if not smart_filter
                            or listing_is_relevant(item, product_name, manufacturer, extra_query)
                        ]
                        fresh = [item for item in matching if item.listing_id not in seen]
                        shown = matching if first_scan else fresh
                        for item in reversed(shown):
                            self.emit("listing", item)
                        for item in fresh:
                            if max_price is not None and item.price is None:
                                continue
                            wants_action = automation.send_message or automation.open_checkout
                            if wants_action and actions_done < automation.max_actions:
                                # Считаем попытку сразу, чтобы не дублировать сообщения
                                # или заказ после ошибки на следующем цикле.
                                actions_done += 1
                                try:
                                    automate_listing(context, item, automation, self.emit)
                                except Exception as exc:
                                    self.emit("automation_error", f"{item.title}: {exc}")
                        seen.update(item.listing_id for item in items)
                        save_seen(seen, profile_slot)
                        self.emit(
                            "status",
                            f"Подходящих: {len(matching)} • проверено: {len(items)} • "
                            f"отсеяно: {len(items) - len(matching)} • новых: {len(fresh)}",
                        )
                        first_scan = False

                    delay = max(MIN_INTERVAL_SECONDS, interval) + random.randint(0, 20)
                    if self.stop_event.wait(delay):
                        break
                context.close()
        except Exception as exc:
            self.emit("error", str(exc))
        finally:
            self.emit("stopped", None)


class AvitoMonitorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Поиск объявлений Avito")
        self.root.geometry("900x760")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker = MonitorWorker(self.events.put)
        self.listing_urls: dict[str, str] = {}
        self.login_active = False
        self.auto_opened_results = False

        menu = tk.Menu(root)
        actions_menu = tk.Menu(menu, tearoff=False)
        actions_menu.add_command(label="Запустить", command=self.start)
        actions_menu.add_command(label="Остановить", command=self.stop)
        actions_menu.add_separator()
        actions_menu.add_command(label="Выход", command=self.close)
        menu.add_cascade(label="Управление", menu=actions_menu)
        history_menu = tk.Menu(menu, tearoff=False)
        history_menu.add_command(label="Очистить просмотренные", command=self.clear_seen)
        history_menu.add_command(label="Очистить список на экране", command=self.clear_results)
        menu.add_cascade(label="История", menu=history_menu)
        root.configure(menu=menu)

        frame = ttk.Frame(root, padding=14)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Монитор новых объявлений", font=("TkDefaultFont", 15, "bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 10)
        )

        ttk.Label(frame, text="Ссылка на категорию").grid(row=1, column=0, sticky="w", pady=4)
        self.category = ttk.Entry(frame)
        self.category.insert(0, "https://www.avito.ru/all")
        self.category.grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)

        ttk.Label(frame, text="Что искать").grid(row=2, column=0, sticky="w", pady=4)
        self.query = ttk.Entry(frame)
        self.query.insert(0, "оперативная память")
        self.query.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Цена до, ₽").grid(row=2, column=2, sticky="e", padx=(12, 4), pady=4)
        self.max_price = ttk.Entry(frame, width=14)
        self.max_price.grid(row=2, column=3, sticky="ew", pady=4)

        ttk.Label(frame, text="Интервал, сек").grid(row=3, column=0, sticky="w", pady=4)
        self.interval = ttk.Spinbox(frame, from_=60, to=86400, increment=60, width=10)
        self.interval.set("300")
        self.interval.grid(row=3, column=1, sticky="w", pady=4)

        self.visible_browser = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="Показывать браузер (полезно при первой проверке)",
            variable=self.visible_browser,
        ).grid(row=3, column=2, columnspan=2, sticky="w", padx=(12, 0))

        controls = ttk.Frame(frame)
        controls.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 8))
        self.start_button = ttk.Button(controls, text="Запустить поиск", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Остановить", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(controls, text="Очистить просмотренные", command=self.clear_seen).pack(side="left")

        automation_frame = ttk.LabelFrame(frame, text="Автобронь", padding=10)
        automation_frame.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(2, 10))
        automation_frame.columnconfigure(1, weight=1)

        self.auto_message = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            automation_frame,
            text="Отправлять продавцу просьбу о брони",
            variable=self.auto_message,
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(automation_frame, text="Сообщение").grid(row=1, column=0, sticky="w", pady=4)
        self.message_text = ttk.Entry(automation_frame)
        self.message_text.insert(0, "Здравствуйте! Готов купить. Пожалуйста, поставьте объявление в бронь.")
        self.message_text.grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)

        self.auto_checkout = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            automation_frame,
            text="Открывать оформление доставки",
            variable=self.auto_checkout,
        ).grid(row=2, column=0, columnspan=2, sticky="w")

        ttk.Label(automation_frame, text="Макс. действий за запуск").grid(
            row=2, column=2, sticky="e", padx=(12, 4)
        )
        self.max_actions = ttk.Spinbox(automation_frame, from_=1, to=10, width=5)
        self.max_actions.set("1")
        self.max_actions.grid(row=2, column=3, sticky="w")

        self.auto_purchase = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            automation_frame,
            text="Нажимать финальную кнопку заказа автоматически",
            variable=self.auto_purchase,
        ).grid(row=3, column=0, columnspan=4, sticky="w")

        self.allow_charge = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            automation_frame,
            text="Разрешаю списание через сохранённый способ оплаты",
            variable=self.allow_charge,
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(3, 0))

        self.status = tk.StringVar(value="Готов")
        ttk.Label(frame, textvariable=self.status).grid(row=6, column=0, columnspan=4, sticky="w", pady=4)

        self.results = tk.Listbox(frame, height=18)
        self.results.grid(row=7, column=0, columnspan=4, sticky="nsew", pady=4)
        frame.rowconfigure(7, weight=1)
        self.results.bind("<Double-Button-1>", self.open_selected)
        ttk.Label(frame, text="Двойной клик открывает объявление").grid(
            row=8, column=0, columnspan=4, sticky="w"
        )

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(150, self.process_events)

    def start(self) -> None:
        try:
            max_price = int(self.max_price.get()) if self.max_price.get().strip() else None
            interval = int(self.interval.get())
            max_actions = int(self.max_actions.get())
            url = build_search_url(self.category.get(), self.query.get(), max_price)
            if max_price is not None and max_price < 0:
                raise ValueError("Цена не может быть отрицательной")
            if interval < MIN_INTERVAL_SECONDS:
                raise ValueError(f"Минимальный интервал — {MIN_INTERVAL_SECONDS} секунд")
            if not 1 <= max_actions <= 10:
                raise ValueError("Количество действий должно быть от 1 до 10")
            if self.auto_message.get() and not self.message_text.get().strip():
                raise ValueError("Укажи текст сообщения продавцу")
            if self.auto_purchase.get() and not self.auto_checkout.get():
                raise ValueError("Для автоматического заказа включи оформление доставки")
            if self.auto_purchase.get() and not self.allow_charge.get():
                raise ValueError("Подтверди разрешение списания")
            if (self.auto_message.get() or self.auto_checkout.get()) and not self.visible_browser.get():
                raise ValueError("Для автоброни оставь видимый браузер включённым")
        except ValueError as exc:
            messagebox.showerror("Проверь параметры", str(exc))
            return

        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        automation = AutomationSettings(
            send_message=self.auto_message.get(),
            message_text=self.message_text.get().strip(),
            open_checkout=self.auto_checkout.get(),
            confirm_purchase=self.auto_purchase.get(),
            max_actions=max_actions,
        )
        self.worker.start(
            url, max_price, interval, 1, "Другой товар", "Любой производитель", "", False,
            self.visible_browser.get(), "Brave", 1, automation,
        )

    def stop(self) -> None:
        self.worker.stop()
        self.status.set("Останавливаю…")

    def clear_seen(self) -> None:
        try:
            SEEN_FILE.unlink(missing_ok=True)
            self.status.set("История очищена")
        except OSError as exc:
            messagebox.showerror("Ошибка", str(exc))

    def clear_results(self) -> None:
        self.results.delete(0, tk.END)
        self.listing_urls.clear()

    def open_selected(self, _event: object = None) -> None:
        selection = self.results.curselection()
        if selection:
            text = self.results.get(selection[0])
            url = self.listing_urls.get(text)
            if url:
                webbrowser.open(url)

    def process_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "listing":
                item = payload
                assert isinstance(item, Listing)
                text = f"{item.display_price} — {item.title}"
                self.listing_urls[text] = item.url
                self.results.insert(0, text)
                self.root.bell()
            elif event == "status":
                self.status.set(str(payload))
            elif event == "automation":
                self.status.set(str(payload))
                self.root.bell()
            elif event == "automation_error":
                self.status.set("Ошибка автоброни")
                messagebox.showwarning("Автобронь не выполнена", str(payload))
            elif event == "error":
                self.status.set("Ошибка")
                messagebox.showerror("Монитор остановлен", str(payload))
            elif event == "challenge":
                self.status.set("Avito ждёт ручную проверку")
                self.root.bell()
                messagebox.showinfo(
                    "Нужна проверка Avito",
                    "Пройди проверку в открытом окне браузера. После этого монитор продолжит работу сам.",
                )
            elif event == "stopped":
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
        self.root.after(150, self.process_events)

    def close(self) -> None:
        self.worker.stop()
        self.root.destroy()


class ModernAvitoMonitorApp:
    BG = "#0b0f12"
    CARD = "#111714"
    FIELD = "#080c0e"
    TEXT = "#e8ecea"
    MUTED = "#7f8a84"
    ACCENT = "#20b86a"

    def __init__(self, root: tk.Misc, profile_slot: int = 1) -> None:
        self.root = root
        self.profile_slot = profile_slot
        self.second_window: tk.Toplevel | None = None
        self.root.title(f"Avito Parts Hunter — монитор {profile_slot}")
        self.root.geometry("1020x720")
        self.root.minsize(860, 620)
        self.root.configure(bg=self.BG)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker = MonitorWorker(self.events.put)
        self.listing_urls: dict[str, str] = {}
        self.login_active = False
        self.auto_opened_results = False
        self._configure_style()

        self.city_var = tk.StringVar(value="Москва")
        self.smart_query_var = tk.StringVar(value="оперативка 2x16 32gb")
        self.product_var = tk.StringVar(value="Оперативная память")
        self.manufacturer_var = tk.StringVar(value="Любой производитель")
        self.extra_var = tk.StringVar(value="")
        self.price_var = tk.StringVar(value="")
        self.interval_var = tk.StringVar(value="300")
        self.pages_var = tk.StringVar(value="3")
        self.smart_filter_var = tk.BooleanVar(value=True)
        self.browser_var = tk.StringVar(value="Brave")
        self.visible_browser = tk.BooleanVar(value=True)
        self.auto_message = tk.BooleanVar(value=False)
        self.auto_checkout = tk.BooleanVar(value=False)
        self.auto_purchase = tk.BooleanVar(value=False)
        self.allow_charge = tk.BooleanVar(value=False)
        self.message_var = tk.StringVar(
            value="Здравствуйте! Готов купить. Пожалуйста, поставьте объявление в бронь."
        )
        self.max_actions_var = tk.StringVar(value="1")
        self.preview_var = tk.StringVar()
        self.status = tk.StringVar(value="Готов к поиску")

        shell = ttk.Frame(root)
        shell.pack(fill="both", expand=True)

        sidebar = ttk.Frame(shell, style="Sidebar.TFrame", width=190, padding=(10, 18))
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        ttk.Label(sidebar, text="PARTS\nHUNTER", style="SidebarTitle.TLabel").pack(anchor="w", padx=8, pady=(0, 22))
        ttk.Label(sidebar, text=f"МОНИТОР #{profile_slot}", style="SidebarMuted.TLabel").pack(
            anchor="w", padx=8, pady=(0, 10)
        )

        content = ttk.Frame(shell, padding=(18, 14))
        content.pack(side="left", fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

        self.page_title_var = tk.StringVar(value="Умный поиск")
        header = ttk.Frame(content)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(header, textvariable=self.page_title_var, style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Avito • комплектующие", style="Muted.TLabel").pack(
            side="left", padx=14, pady=(8, 0)
        )

        self.pages: dict[str, ttk.Frame] = {}
        for page_name in ("search", "automation", "results", "account"):
            page_frame = ttk.Frame(content)
            page_frame.grid(row=1, column=0, sticky="nsew")
            page_frame.columnconfigure(0, weight=1)
            page_frame.rowconfigure(0, weight=1)
            self.pages[page_name] = page_frame

        self.nav_buttons: dict[str, ttk.Button] = {}
        nav_items = (
            ("search", "⌕  Умный поиск", "Умный поиск"),
            ("automation", "⚡  Автобронь", "Автобронь"),
            ("results", "▤  Объявления", "Найденные объявления"),
            ("account", "●  Аккаунт Avito", "Аккаунт Avito"),
        )
        for key, label, title in nav_items:
            button = ttk.Button(
                sidebar,
                text=label,
                style="Sidebar.TButton",
                command=lambda k=key, t=title: self.show_page(k, t),
            )
            button.pack(fill="x", pady=3)
            self.nav_buttons[key] = button
        if self.profile_slot == 1:
            ttk.Button(
                sidebar,
                text="＋  Второе окно",
                style="Sidebar.TButton",
                command=self.open_second_monitor,
            ).pack(side="bottom", fill="x", pady=3)

        search = ttk.LabelFrame(
            self.pages["search"], text="  Настройка поиска  ", style="Card.TLabelframe", padding=18
        )
        search.grid(row=0, column=0, sticky="nsew")
        search.columnconfigure(1, weight=1)
        search.columnconfigure(3, weight=1)

        self._label(search, "Умный запрос", 0, 0)
        smart_entry = ttk.Entry(search, textvariable=self.smart_query_var)
        smart_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(8, 8), pady=5)
        smart_entry.bind("<Return>", self.apply_smart_query)
        ttk.Button(search, text="Распознать", style="Accent.TButton", command=self.apply_smart_query).grid(
            row=0, column=3, sticky="ew", pady=5
        )

        self._label(search, "Город", 1, 0)
        self.city_box = ttk.Combobox(search, textvariable=self.city_var, values=tuple(CITIES), state="readonly")
        self.city_box.grid(row=1, column=1, sticky="ew", padx=(8, 14), pady=5)

        self._label(search, "Браузер", 1, 2)
        self.browser_box = ttk.Combobox(
            search, textvariable=self.browser_var, values=("Brave", "Chromium"), state="readonly", width=14
        )
        self.browser_box.grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._label(search, "Комплектующая", 2, 0)
        self.product_box = ttk.Combobox(
            search, textvariable=self.product_var, values=COMPONENT_NAMES, state="readonly"
        )
        self.product_box.grid(row=2, column=1, sticky="ew", padx=(8, 14), pady=5)
        self.product_box.bind("<<ComboboxSelected>>", self.on_product_changed)

        self._label(search, "Производитель", 2, 2)
        self.manufacturer_box = ttk.Combobox(search, textvariable=self.manufacturer_var)
        self.manufacturer_box.grid(row=2, column=3, sticky="ew", padx=(8, 0), pady=5)
        self.manufacturer_box.bind("<<ComboboxSelected>>", self.on_manufacturer_changed)

        self._label(search, "Характеристики", 3, 0)
        ttk.Entry(search, textvariable=self.extra_var).grid(
            row=3, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=5
        )

        self._label(search, "Цена до, ₽", 4, 0)
        ttk.Entry(search, textvariable=self.price_var).grid(row=4, column=1, sticky="ew", padx=(8, 14), pady=5)
        self._label(search, "Интервал, сек", 4, 2)
        ttk.Spinbox(search, from_=60, to=86400, increment=60, textvariable=self.interval_var).grid(
            row=4, column=3, sticky="ew", padx=(8, 0), pady=5
        )

        self._label(search, "Страниц за цикл", 5, 0)
        ttk.Spinbox(search, from_=1, to=20, textvariable=self.pages_var).grid(
            row=5, column=1, sticky="ew", padx=(8, 14), pady=5
        )
        ttk.Checkbutton(
            search, text="Отсекать неподходящие объявления", variable=self.smart_filter_var
        ).grid(row=5, column=2, columnspan=2, sticky="w", pady=5)

        ttk.Checkbutton(
            search, text="Показывать окно Brave", variable=self.visible_browser
        ).grid(row=6, column=0, columnspan=4, sticky="w", pady=(7, 2))
        ttk.Label(search, textvariable=self.preview_var, style="Hint.TLabel", wraplength=620).grid(
            row=7, column=0, columnspan=4, sticky="w", pady=(5, 0)
        )

        automation = ttk.LabelFrame(
            self.pages["automation"], text="  Действия с подходящими объявлениями  ",
            style="Card.TLabelframe", padding=18,
        )
        automation.grid(row=0, column=0, sticky="nsew")
        automation.columnconfigure(0, weight=1)
        self._toggle_row(
            automation, 0, "Сообщение продавцу", "Автоматически попросить поставить товар в бронь", self.auto_message
        )
        ttk.Entry(automation, textvariable=self.message_var).grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._toggle_row(
            automation, 2, "Открыть оформление", "Перейти к оформлению Авито Доставки", self.auto_checkout
        )
        self._toggle_row(
            automation, 3, "Подтвердить заказ", "Нажать финальную кнопку заказа", self.auto_purchase
        )
        self._toggle_row(
            automation, 4, "Разрешить списание", "Использовать сохранённый способ оплаты", self.allow_charge
        )
        limit_row = ttk.Frame(automation, style="Card.TFrame")
        limit_row.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(limit_row, text="Лимит действий:", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(limit_row, from_=1, to=10, width=5, textvariable=self.max_actions_var).pack(
            side="left", padx=8
        )

        controls = ttk.Frame(search, style="Card.TFrame")
        controls.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(18, 0))
        controls.columnconfigure(4, weight=1)
        self.start_button = ttk.Button(
            controls, text="▶  Старт", style="Accent.TButton", command=self.start
        )
        self.start_button.grid(row=0, column=0, padx=(0, 7))
        self.stop_button = ttk.Button(
            controls, text="■  Стоп", style="Danger.TButton", command=self.stop, state="disabled"
        )
        self.stop_button.grid(row=0, column=1, padx=(0, 7))
        ttk.Button(controls, text="Очистить историю", command=self.clear_seen).grid(
            row=0, column=2, padx=(0, 7)
        )
        results_card = ttk.LabelFrame(
            self.pages["results"], text="  Подходящие объявления  ", style="Card.TLabelframe", padding=10
        )
        results_card.grid(row=0, column=0, sticky="nsew")
        results_card.columnconfigure(0, weight=1)
        results_card.rowconfigure(0, weight=1)
        self.results = ttk.Treeview(results_card, columns=("price", "title"), show="headings", selectmode="browse")
        self.results.heading("price", text="Цена")
        self.results.heading("title", text="Объявление")
        self.results.column("price", width=130, anchor="e", stretch=False)
        self.results.column("title", width=760, anchor="w")
        self.results.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(results_card, orient="vertical", command=self.results.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results.configure(yscrollcommand=scrollbar.set)
        self.results.bind("<Double-Button-1>", self.open_selected)

        account = ttk.LabelFrame(
            self.pages["account"], text="  Сохранённый вход  ", style="Card.TLabelframe", padding=22
        )
        account.grid(row=0, column=0, sticky="nsew")
        account.columnconfigure(0, weight=1)
        ttk.Label(
            account,
            text="Открой Brave и войди в аккаунт Avito.\n"
                 "Скрипт проверит вход, сохранит сессию и сам закроет окно.",
            style="Card.TLabel",
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 18))
        self.login_button = ttk.Button(
            account, text="Войти в Avito через Brave", style="Accent.TButton", command=self.open_login
        )
        self.login_button.grid(row=1, column=0, sticky="w")
        ttk.Label(
            account,
            text="Пароль не сохраняется в скрипте. Мониторы #1 и #2 используют отдельные профили.",
            style="Hint.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(14, 0))

        status_bar = ttk.Frame(content, style="Status.TFrame", padding=(10, 7))
        status_bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(status_bar, textvariable=self.status, style="Status.TLabel").pack(side="left")
        ttk.Label(status_bar, text="Двойной клик — открыть объявление", style="StatusMuted.TLabel").pack(side="right")

        for variable in (self.city_var, self.manufacturer_var, self.extra_var, self.price_var):
            variable.trace_add("write", lambda *_: self.update_preview())
        self.on_product_changed()
        self.show_page("search", "Умный поиск")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(150, self.process_events)

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD)
        style.configure("Option.TFrame", background="#142019", relief="flat")
        style.configure(
            "OptionTitle.TLabel", background="#142019", foreground="#eaf5ee",
            font=("Segoe UI Semibold", 10),
        )
        style.configure(
            "OptionDesc.TLabel", background="#142019", foreground="#718078",
            font=("Segoe UI", 8),
        )
        style.configure("Sidebar.TFrame", background="#070a0c")
        style.configure(
            "SidebarTitle.TLabel", background="#070a0c", foreground="#ffffff",
            font=("Segoe UI Semibold", 16),
        )
        style.configure(
            "SidebarMuted.TLabel", background="#070a0c", foreground="#627068",
            font=("Segoe UI Semibold", 8),
        )
        style.configure(
            "Sidebar.TButton", background="#070a0c", foreground="#a6afa9",
            font=("Segoe UI", 10), padding=(12, 10), anchor="w", borderwidth=0,
        )
        style.map("Sidebar.TButton", background=[("active", "#172234")], foreground=[("active", "#ffffff")])
        style.configure(
            "SidebarActive.TButton", background="#13251b", foreground="#73e5a4",
            font=("Segoe UI Semibold", 10), padding=(12, 10), anchor="w", borderwidth=0,
        )
        style.map("SidebarActive.TButton", background=[("active", "#1e3a2f")])
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.CARD, foreground=self.TEXT)
        style.configure("Title.TLabel", background=self.BG, foreground="#ffffff", font=("Segoe UI Semibold", 20))
        style.configure("Muted.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Hint.TLabel", background=self.CARD, foreground=self.MUTED, font=("Segoe UI", 8))
        style.configure("Card.TLabelframe", background=self.CARD, bordercolor="#334155", relief="solid")
        style.configure("Card.TLabelframe.Label", background=self.CARD, foreground="#ffffff", font=("Segoe UI Semibold", 11))
        style.configure("TEntry", fieldbackground=self.FIELD, foreground=self.TEXT, insertcolor=self.TEXT, bordercolor="#334155", padding=7)
        style.configure("TCombobox", fieldbackground=self.FIELD, foreground=self.TEXT, arrowcolor=self.TEXT, padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", self.FIELD)], foreground=[("readonly", self.TEXT)])
        style.configure("TSpinbox", fieldbackground=self.FIELD, foreground=self.TEXT, arrowcolor=self.TEXT, padding=6)
        style.configure("TCheckbutton", background=self.CARD, foreground=self.TEXT, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", self.CARD)], foreground=[("active", "#ffffff")])
        style.configure("TButton", background="#334155", foreground="#ffffff", padding=(13, 8), borderwidth=0)
        style.map(
            "TButton",
            background=[("active", "#475569"), ("disabled", "#1e293b")],
            foreground=[("disabled", "#64748b")],
        )
        style.configure("Accent.TButton", background=self.ACCENT, foreground="#ffffff", font=("Segoe UI Semibold", 10), padding=(18, 9))
        style.map(
            "Accent.TButton",
            background=[("active", "#2ed67e"), ("disabled", self.ACCENT)],
            foreground=[("disabled", "#ffffff")],
        )
        style.configure("Running.TButton", background="#167747", foreground="#ffffff", font=("Segoe UI Semibold", 10), padding=(18, 9))
        style.map("Running.TButton", background=[("disabled", "#167747")], foreground=[("disabled", "#ffffff")])
        style.configure("Switch.TCheckbutton", background="#142019", foreground=self.ACCENT, padding=6)
        style.map("Switch.TCheckbutton", background=[("active", "#142019")])
        style.configure("Danger.TButton", background="#b91c1c", foreground="#ffffff")
        style.map("Danger.TButton", background=[("active", "#dc2626"), ("disabled", "#3f2529")])
        style.configure("Treeview", background=self.FIELD, fieldbackground=self.FIELD, foreground=self.TEXT, rowheight=30, borderwidth=0)
        style.configure("Treeview.Heading", background="#263449", foreground="#ffffff", font=("Segoe UI Semibold", 10), padding=7)
        style.map("Treeview", background=[("selected", "#334e68")])
        style.configure("Status.TFrame", background="#111c2e")
        style.configure("Status.TLabel", background="#111c2e", foreground="#7dd3fc")
        style.configure("StatusMuted.TLabel", background="#111c2e", foreground=self.MUTED)

    @staticmethod
    def _label(parent: ttk.Widget, text: str, row: int, column: int) -> None:
        ttk.Label(parent, text=text, style="Card.TLabel").grid(row=row, column=column, sticky="w", pady=5)

    @staticmethod
    def _toggle_row(
        parent: ttk.Widget,
        row: int,
        title: str,
        description: str,
        variable: tk.BooleanVar,
    ) -> None:
        option = ttk.Frame(parent, style="Option.TFrame", padding=(12, 9))
        option.grid(row=row, column=0, sticky="ew", pady=3)
        option.columnconfigure(0, weight=1)
        ttk.Label(option, text=title, style="OptionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(option, text=description, style="OptionDesc.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(option, variable=variable, style="Switch.TCheckbutton").grid(
            row=0, column=1, rowspan=2, sticky="e", padx=(12, 0)
        )

    def show_page(self, page_name: str, title: str) -> None:
        self.pages[page_name].tkraise()
        self.page_title_var.set(title)
        for key, button in self.nav_buttons.items():
            button.configure(style="SidebarActive.TButton" if key == page_name else "Sidebar.TButton")

    def apply_smart_query(self, _event: object = None) -> None:
        value = self.smart_query_var.get().strip()
        if not value:
            messagebox.showerror("Пустой запрос", "Напиши, что искать, например: оперативка 2x16 32gb")
            return
        product, manufacturer, extra = detect_smart_query(value)
        if product == "Другой товар":
            messagebox.showinfo(
                "Тип не распознан",
                "Не удалось определить комплектующую. Выбери её вручную, а характеристики оставь в поле ниже.",
            )
            self.product_var.set("Другой товар")
            self.on_product_changed()
            self.extra_var.set(extra or value)
            return
        self.product_var.set(product)
        self.on_product_changed()
        self.manufacturer_var.set(manufacturer)
        self.extra_var.set(extra)
        details = f"Распознано: {product}"
        if manufacturer != "Любой производитель":
            details += f" • {manufacturer}"
        if extra:
            details += f" • {extra}"
        self.status.set(details)

    def on_product_changed(self, _event: object = None) -> None:
        makers = PRODUCTS[self.product_var.get()][1]
        self.manufacturer_box.configure(values=("Любой производитель", *makers, "Другой — ввести вручную"))
        self.manufacturer_var.set("Любой производитель")
        self.update_preview()

    def on_manufacturer_changed(self, _event: object = None) -> None:
        if self.manufacturer_var.get() == "Другой — ввести вручную":
            self.manufacturer_var.set("")
            self.manufacturer_box.focus_set()

    def search_url(self, max_price: int | None) -> str:
        city = CITIES[self.city_var.get()]
        product_query = PRODUCTS[self.product_var.get()][0]
        manufacturer = self.manufacturer_var.get().strip()
        parts = [product_query]
        if manufacturer and manufacturer != "Любой производитель":
            parts.append(manufacturer)
        if self.extra_var.get().strip():
            parts.append(self.extra_var.get().strip())
        query = " ".join(part for part in parts if part)
        if not query:
            raise ValueError("Для «Другого товара» укажи название в поле «Доп. слова»")
        base = f"https://www.avito.ru/{city}/tovary_dlya_kompyutera"
        return build_search_url(base, query, max_price)

    def update_preview(self) -> None:
        try:
            price = int(self.price_var.get()) if self.price_var.get().strip().isdigit() else None
            product = PRODUCTS[self.product_var.get()][0]
            manufacturer = self.manufacturer_var.get().strip()
            query = " ".join(
                value for value in (product, manufacturer if manufacturer != "Любой производитель" else "", self.extra_var.get().strip()) if value
            )
            self.preview_var.set(f"Запрос: {query or 'укажи название товара'}" + (f"  •  до {price:,} ₽".replace(",", " ") if price else ""))
        except (KeyError, ValueError):
            self.preview_var.set("Заполни параметры поиска")

    def start(self) -> None:
        try:
            if self.login_active:
                raise ValueError("Сначала закончи вход в Avito и закрой окно Brave")
            max_price = int(self.price_var.get()) if self.price_var.get().strip() else None
            interval = int(self.interval_var.get())
            max_pages = int(self.pages_var.get())
            max_actions = int(self.max_actions_var.get())
            url = self.search_url(max_price)
            if max_price is not None and max_price <= 0:
                raise ValueError("Максимальная цена должна быть больше нуля")
            if interval < MIN_INTERVAL_SECONDS:
                raise ValueError(f"Минимальный интервал — {MIN_INTERVAL_SECONDS} секунд")
            if not 1 <= max_pages <= 20:
                raise ValueError("Количество страниц должно быть от 1 до 20")
            if not 1 <= max_actions <= 10:
                raise ValueError("Лимит действий должен быть от 1 до 10")
            if self.auto_message.get() and not self.message_var.get().strip():
                raise ValueError("Укажи текст сообщения продавцу")
            if self.auto_purchase.get() and not self.auto_checkout.get():
                raise ValueError("Для автозаказа включи оформление доставки")
            if self.auto_purchase.get() and not self.allow_charge.get():
                raise ValueError("Подтверди разрешение списания")
            if (self.auto_message.get() or self.auto_checkout.get()) and not self.visible_browser.get():
                raise ValueError("Для автоброни оставь окно Brave включённым")
        except ValueError as exc:
            messagebox.showerror("Проверь параметры", str(exc))
            return

        automation = AutomationSettings(
            send_message=self.auto_message.get(),
            message_text=self.message_var.get().strip(),
            open_checkout=self.auto_checkout.get(),
            confirm_purchase=self.auto_purchase.get(),
            max_actions=max_actions,
        )
        self.results.delete(*self.results.get_children())
        self.listing_urls.clear()
        self.auto_opened_results = False
        self.start_button.configure(state="disabled", text="●  Поиск работает", style="Running.TButton")
        self.stop_button.configure(state="normal")
        self.login_button.configure(state="disabled")
        self.worker.start(
            url,
            max_price,
            interval,
            max_pages,
            self.product_var.get(),
            self.manufacturer_var.get().strip(),
            self.extra_var.get().strip(),
            self.smart_filter_var.get(),
            self.visible_browser.get(),
            self.browser_var.get(),
            self.profile_slot,
            automation,
        )

    def open_login(self) -> None:
        if self.worker.thread is not None and self.worker.thread.is_alive():
            messagebox.showinfo("Монитор работает", "Сначала останови поиск, затем открой вход в Avito.")
            return
        if self.login_active:
            return
        browser_name = self.browser_var.get()
        executable = system_browser(browser_name)
        if browser_name == "Brave" and not executable:
            messagebox.showerror("Brave не найден", "Установи Brave и снова нажми «Войти в Avito».")
            return
        self.login_active = True
        self.login_button.configure(state="disabled", text="Окно входа открыто")
        self.status.set(f"Войди в Avito в {browser_name}; окно закроется после успешной проверки")
        threading.Thread(
            target=self._login_worker,
            args=(browser_name, executable),
            daemon=True,
        ).start()

    def _login_worker(self, browser_name: str, executable: str | None) -> None:
        try:
            with sync_playwright() as playwright:
                options: dict[str, object] = {
                    "headless": False,
                    "locale": "ru-RU",
                    "viewport": {"width": 1280, "height": 900},
                }
                if executable:
                    options["executable_path"] = executable
                context = playwright.chromium.launch_persistent_context(
                    str(browser_profile_dir(browser_name, self.profile_slot)),
                    **options,
                )
                closed = threading.Event()
                context.on("close", lambda: closed.set())
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://www.avito.ru/profile", wait_until="domcontentloaded", timeout=60_000)
                self.events.put(("login_status", "Avito открыт. Через секунду обновляю страницу…"))
                page.wait_for_timeout(1_000)
                page.reload(wait_until="domcontentloaded", timeout=60_000)
                self.events.put(("login_status", f"Войди в Avito в {browser_name} — проверю вход автоматически"))
                deadline = time.monotonic() + CHALLENGE_WAIT_SECONDS
                challenge_seen = False
                cleared_at: float | None = None
                stuck_since: float | None = None
                reloads = 0
                while time.monotonic() < deadline:
                    if closed.wait(1):
                        raise RuntimeError("Окно Brave закрыто до подтверждения входа в аккаунт")
                    if is_avito_logged_in(page):
                        save_auth_state(context)
                        self.events.put(("login_done", browser_name))
                        context.close()
                        return
                    if page_has_challenge(page):
                        challenge_seen = True
                        cleared_at = None
                        self.events.put(("login_status", "Avito проверяет IP. Жду завершения проверки…"))
                        continue
                    if challenge_seen:
                        if cleared_at is None:
                            cleared_at = time.monotonic()
                        elif time.monotonic() - cleared_at >= 1 and reloads < 4:
                            reloads += 1
                            self.events.put(("login_status", f"Проверка завершена. Обновляю Avito ({reloads}/4)…"))
                            page.goto("https://www.avito.ru/profile", wait_until="domcontentloaded", timeout=60_000)
                            cleared_at = time.monotonic()
                    else:
                        try:
                            body = normalize_search_text(page.locator("body").inner_text(timeout=3_000))
                        except Exception:
                            body = ""
                        looks_stuck = len(body) < 80 or body in {"загрузка", "подождите", "loading"}
                        if looks_stuck:
                            if stuck_since is None:
                                stuck_since = time.monotonic()
                            elif time.monotonic() - stuck_since >= 10 and reloads < 4:
                                reloads += 1
                                self.events.put(("login_status", f"Страница зависла. Обновляю Avito ({reloads}/4)…"))
                                page.goto("https://www.avito.ru/profile", wait_until="domcontentloaded", timeout=60_000)
                                stuck_since = time.monotonic()
                        else:
                            stuck_since = None
                context.close()
                raise RuntimeError("Вход не подтверждён за 10 минут")
        except Exception as exc:
            self.events.put(("login_error", str(exc)))

    def open_second_monitor(self) -> None:
        if self.second_window is not None and self.second_window.winfo_exists():
            self.second_window.deiconify()
            self.second_window.lift()
            return
        self.second_window = tk.Toplevel(self.root)
        ModernAvitoMonitorApp(self.second_window, profile_slot=2)

    def stop(self) -> None:
        self.worker.stop()
        self.status.set("Останавливаю монитор…")

    def clear_seen(self) -> None:
        try:
            seen_file(self.profile_slot).unlink(missing_ok=True)
            self.status.set("История просмотренных очищена")
        except OSError as exc:
            messagebox.showerror("Ошибка", str(exc))

    def open_selected(self, _event: object = None) -> None:
        item_id = self.results.focus()
        if item_id and item_id in self.listing_urls:
            webbrowser.open(self.listing_urls[item_id])

    def process_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "listing":
                item = payload
                assert isinstance(item, Listing)
                row_id = self.results.insert("", 0, values=(item.display_price, item.title))
                self.listing_urls[row_id] = item.url
                if not self.auto_opened_results:
                    self.auto_opened_results = True
                    self.show_page("results", "Найденные объявления")
                self.root.bell()
            elif event in {"status", "automation"}:
                self.status.set(str(payload))
            elif event == "automation_error":
                self.status.set("Автобронь требует внимания")
                messagebox.showwarning("Автобронь не выполнена", str(payload))
            elif event == "error":
                self.status.set("Монитор остановлен с ошибкой")
                messagebox.showerror("Монитор остановлен", str(payload))
            elif event == "challenge":
                self.status.set("Пройди проверку в Brave")
                messagebox.showinfo(
                    "Нужна проверка Avito",
                    "Пройди проверку в открытом Brave. Монитор продолжит работу автоматически.",
                )
            elif event == "login_status":
                self.status.set(str(payload))
            elif event == "login_done":
                self.login_active = False
                self.login_button.configure(state="normal", text="Войти в Avito")
                self.status.set("Вход сохранён. Можно запускать монитор")
            elif event == "login_error":
                self.login_active = False
                self.login_button.configure(state="normal", text="Войти в Avito")
                self.status.set("Не удалось открыть окно входа")
                messagebox.showerror("Ошибка входа", str(payload))
            elif event == "stopped":
                self.start_button.configure(state="normal", text="▶  Старт", style="Accent.TButton")
                self.stop_button.configure(state="disabled")
                self.login_button.configure(state="normal")
        self.root.after(150, self.process_events)

    def close(self) -> None:
        self.worker.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ModernAvitoMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
