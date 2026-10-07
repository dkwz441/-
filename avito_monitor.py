from __future__ import annotations

import json
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


def load_seen() -> set[str]:
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        return {str(item) for item in data}
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        return set()


def save_seen(seen: set[str]) -> None:
    # Ограничиваем файл, чтобы многомесячный мониторинг не раздувал его бесконечно.
    SEEN_FILE.write_text(
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


def system_browser() -> str | None:
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        executable = shutil.which(name)
        if executable:
            return executable
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
        automation: AutomationSettings,
    ) -> None:
        self.stop()
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run,
            args=(url, max_price, interval, visible, automation),
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
        automation: AutomationSettings,
    ) -> None:
        seen = load_seen()
        actions_done = 0
        try:
            with sync_playwright() as playwright:
                launch_options: dict[str, object] = {
                    "headless": not visible,
                    "locale": "ru-RU",
                    "viewport": {"width": 1280, "height": 900},
                }
                executable = system_browser()
                if executable:
                    launch_options["executable_path"] = executable
                context: BrowserContext = playwright.chromium.launch_persistent_context(
                    str(PROFILE_DIR),
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
                        save_seen(seen)
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
        self.worker.start(url, max_price, interval, self.visible_browser.get(), automation)

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


def main() -> None:
    root = tk.Tk()
    AvitoMonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
