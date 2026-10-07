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
MIN_INTERVAL_SECONDS = 60
CHALLENGE_WAIT_SECONDS = 600

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
    cards = page.locator('[data-marker="item"]')
    raw_items = cards.evaluate_all(
        """
        cards => cards.map(card => {
          const link = card.querySelector('[data-marker="item-title"], a[itemprop="url"], a[href*="/items/"]');
          const titleNode = card.querySelector('[data-marker="item-title"], [itemprop="name"]');
          const priceNode = card.querySelector('[itemprop="price"], [data-marker="item-price"]');
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
    for item in raw_items:
        listings.append(
            Listing(
                listing_id=str(item["id"]),
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
    while time.monotonic() < deadline and not stop_event.is_set():
        if page.locator('[data-marker="item"]').count() > 0 and not page_has_challenge(page):
            emit("status", "Проверка пройдена, продолжаю мониторинг…")
            return True
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
        visible: bool,
        browser_name: str,
        profile_slot: int,
        automation: AutomationSettings,
    ) -> None:
        self.stop()
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            args=(url, max_price, interval, visible, browser_name, profile_slot, automation),
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
        visible: bool,
        browser_name: str,
        profile_slot: int,
        automation: AutomationSettings,
    ) -> None:
        seen = load_seen(profile_slot)
        actions_done = 0
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
                profile_name = ".avito-brave-profile" if browser_name == "Brave" else ".avito-browser-profile"
                profile_dir = APP_DIR / f"{profile_name}-{profile_slot}"
                context: BrowserContext = playwright.chromium.launch_persistent_context(
                    str(profile_dir),
                    **launch_options,
                )
                page = context.pages[0] if context.pages else context.new_page()
                while not self.stop_event.is_set():
                    self.emit("status", "Проверяю Avito…")
                    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    try:
                        page.locator('[data-marker="item"]').first.wait_for(timeout=20_000)
                    except Exception:
                        if page_has_challenge(page):
                            if not visible:
                                raise RuntimeError(
                                    "Avito запросил проверку. Включи «Показывать браузер» и запусти монитор снова."
                                )
                            if not wait_for_manual_challenge(page, self.stop_event, self.emit):
                                if self.stop_event.is_set():
                                    break
                                raise RuntimeError("Проверка Avito не пройдена за 10 минут.")
                    items = extract_listings(page)
                    if not items:
                        self.emit("status", "Объявления не найдены; возможно, Avito изменил страницу или показал проверку.")
                    else:
                        fresh = [
                            item
                            for item in items
                            if item.listing_id not in seen
                            and (max_price is None or (item.price is not None and item.price <= max_price))
                        ]
                        for item in reversed(fresh):
                            self.emit("listing", item)
                        for item in fresh:
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
                        self.emit("status", f"Проверено: {len(items)}; новых: {len(fresh)}")

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
        self.worker.start(url, max_price, interval, self.visible_browser.get(), "Brave", 1, automation)

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
    BG = "#0f172a"
    CARD = "#182235"
    FIELD = "#0b1220"
    TEXT = "#e5e7eb"
    MUTED = "#94a3b8"
    ACCENT = "#ff6b00"

    def __init__(self, root: tk.Misc, profile_slot: int = 1) -> None:
        self.root = root
        self.profile_slot = profile_slot
        self.second_window: tk.Toplevel | None = None
        self.root.title(f"Avito Parts Hunter — монитор {profile_slot}")
        self.root.geometry("1120x820")
        self.root.minsize(900, 680)
        self.root.configure(bg=self.BG)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker = MonitorWorker(self.events.put)
        self.listing_urls: dict[str, str] = {}
        self._configure_style()

        self.city_var = tk.StringVar(value="Москва")
        self.product_var = tk.StringVar(value="Оперативная память")
        self.manufacturer_var = tk.StringVar(value="Любой производитель")
        self.extra_var = tk.StringVar(value="")
        self.price_var = tk.StringVar(value="")
        self.interval_var = tk.StringVar(value="300")
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

        main = ttk.Frame(root, padding=18)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(3, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        ttk.Label(header, text=f"AVITO PARTS HUNTER  #{profile_slot}", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="комплектующие • новые объявления • автобронь",
            style="Muted.TLabel",
        ).pack(side="left", padx=14, pady=(8, 0))

        search = ttk.LabelFrame(main, text="  Параметры поиска  ", style="Card.TLabelframe", padding=14)
        search.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        search.columnconfigure(1, weight=1)
        search.columnconfigure(3, weight=1)

        self._label(search, "Город", 0, 0)
        self.city_box = ttk.Combobox(search, textvariable=self.city_var, values=tuple(CITIES), state="readonly")
        self.city_box.grid(row=0, column=1, sticky="ew", padx=(8, 14), pady=5)

        self._label(search, "Браузер", 0, 2)
        self.browser_box = ttk.Combobox(
            search, textvariable=self.browser_var, values=("Brave", "Chromium"), state="readonly", width=14
        )
        self.browser_box.grid(row=0, column=3, sticky="ew", padx=(8, 0), pady=5)

        self._label(search, "Комплектующая", 1, 0)
        self.product_box = ttk.Combobox(
            search, textvariable=self.product_var, values=COMPONENT_NAMES, state="readonly"
        )
        self.product_box.grid(row=1, column=1, sticky="ew", padx=(8, 14), pady=5)
        self.product_box.bind("<<ComboboxSelected>>", self.on_product_changed)

        self._label(search, "Производитель", 1, 2)
        self.manufacturer_box = ttk.Combobox(search, textvariable=self.manufacturer_var)
        self.manufacturer_box.grid(row=1, column=3, sticky="ew", padx=(8, 0), pady=5)
        self.manufacturer_box.bind("<<ComboboxSelected>>", self.on_manufacturer_changed)

        self._label(search, "Доп. слова", 2, 0)
        ttk.Entry(search, textvariable=self.extra_var).grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=5
        )

        self._label(search, "Цена до, ₽", 3, 0)
        ttk.Entry(search, textvariable=self.price_var).grid(row=3, column=1, sticky="ew", padx=(8, 14), pady=5)
        self._label(search, "Интервал, сек", 3, 2)
        ttk.Spinbox(search, from_=60, to=86400, increment=60, textvariable=self.interval_var).grid(
            row=3, column=3, sticky="ew", padx=(8, 0), pady=5
        )

        ttk.Checkbutton(
            search, text="Показывать окно Brave", variable=self.visible_browser
        ).grid(row=4, column=0, columnspan=4, sticky="w", pady=(7, 2))
        ttk.Label(search, textvariable=self.preview_var, style="Hint.TLabel", wraplength=620).grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(5, 0)
        )

        automation = ttk.LabelFrame(main, text="  Автобронь  ", style="Card.TLabelframe", padding=14)
        automation.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        automation.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            automation, text="Написать продавцу", variable=self.auto_message
        ).grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(automation, textvariable=self.message_var).grid(row=1, column=0, sticky="ew", pady=(2, 8))
        ttk.Checkbutton(
            automation, text="Открыть оформление доставки", variable=self.auto_checkout
        ).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Checkbutton(
            automation, text="Подтвердить заказ автоматически", variable=self.auto_purchase
        ).grid(row=3, column=0, sticky="w", pady=3)
        ttk.Checkbutton(
            automation, text="Разрешаю списание", variable=self.allow_charge
        ).grid(row=4, column=0, sticky="w", pady=3)
        limit_row = ttk.Frame(automation, style="Card.TFrame")
        limit_row.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(limit_row, text="Лимит действий:", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(limit_row, from_=1, to=10, width=5, textvariable=self.max_actions_var).pack(
            side="left", padx=8
        )

        controls = ttk.Frame(main)
        controls.grid(row=2, column=0, columnspan=2, sticky="ew", pady=14)
        self.start_button = ttk.Button(controls, text="▶  ЗАПУСТИТЬ ПОИСК", style="Accent.TButton", command=self.start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="■  ОСТАНОВИТЬ", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        ttk.Button(controls, text="Очистить просмотренные", command=self.clear_seen).pack(side="left")
        if self.profile_slot == 1:
            ttk.Button(controls, text="＋ ВТОРОЙ МОНИТОР", command=self.open_second_monitor).pack(
                side="right"
            )

        results_card = ttk.LabelFrame(main, text="  Найденные объявления  ", style="Card.TLabelframe", padding=10)
        results_card.grid(row=3, column=0, columnspan=2, sticky="nsew")
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

        status_bar = ttk.Frame(main, style="Status.TFrame", padding=(10, 7))
        status_bar.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(status_bar, textvariable=self.status, style="Status.TLabel").pack(side="left")
        ttk.Label(status_bar, text="Двойной клик — открыть объявление", style="StatusMuted.TLabel").pack(side="right")

        for variable in (self.city_var, self.manufacturer_var, self.extra_var, self.price_var):
            variable.trace_add("write", lambda *_: self.update_preview())
        self.on_product_changed()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(150, self.process_events)

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD)
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
        style.map("TButton", background=[("active", "#475569"), ("disabled", "#1e293b")])
        style.configure("Accent.TButton", background=self.ACCENT, foreground="#ffffff", font=("Segoe UI Semibold", 10), padding=(18, 9))
        style.map("Accent.TButton", background=[("active", "#ff8124"), ("disabled", "#7c3b0e")])
        style.configure("Treeview", background=self.FIELD, fieldbackground=self.FIELD, foreground=self.TEXT, rowheight=30, borderwidth=0)
        style.configure("Treeview.Heading", background="#263449", foreground="#ffffff", font=("Segoe UI Semibold", 10), padding=7)
        style.map("Treeview", background=[("selected", "#334e68")])
        style.configure("Status.TFrame", background="#111c2e")
        style.configure("Status.TLabel", background="#111c2e", foreground="#7dd3fc")
        style.configure("StatusMuted.TLabel", background="#111c2e", foreground=self.MUTED)

    @staticmethod
    def _label(parent: ttk.Widget, text: str, row: int, column: int) -> None:
        ttk.Label(parent, text=text, style="Card.TLabel").grid(row=row, column=column, sticky="w", pady=5)

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
            max_price = int(self.price_var.get()) if self.price_var.get().strip() else None
            interval = int(self.interval_var.get())
            max_actions = int(self.max_actions_var.get())
            url = self.search_url(max_price)
            if max_price is not None and max_price <= 0:
                raise ValueError("Максимальная цена должна быть больше нуля")
            if interval < MIN_INTERVAL_SECONDS:
                raise ValueError(f"Минимальный интервал — {MIN_INTERVAL_SECONDS} секунд")
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
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.worker.start(
            url,
            max_price,
            interval,
            self.visible_browser.get(),
            self.browser_var.get(),
            self.profile_slot,
            automation,
        )

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
            elif event == "stopped":
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
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
