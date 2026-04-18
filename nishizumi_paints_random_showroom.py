#!/usr/bin/env python3
"""Small Trading Paints public showroom downloader test tool."""

from __future__ import annotations

import bz2
import json
import queue
import random
import re
import shutil
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "Nishizumi Paints - Random Showroom Downloader"
APP_USER_AGENT = "nishizumi-paints-random-showroom/0.1"
DEFAULT_SHOWROOM_PARAMS = (
    "sort=popular&ad=DESC&search=&reuse=1&family=1&hasnumber=1&from=everyone&stampednums=1&official_only=0"
)
SHOWROOM_PAGE_SIZE = 24
SHOWROOM_MAX_PAGE_LIMIT = 50
SHOWROOM_COMPRESSED_URL = "https://showroom-assets.tradingpaints.gg/compressed/{scheme_id}.tga.bz2"
SHOWROOM_MIP_URL = "https://showroom-assets.tradingpaints.gg/mips/{scheme_id}.mip"
UNAVAILABLE_STATUS_CODES = {401, 403, 404}


@dataclass(frozen=True)
class ShowroomPaint:
    scheme_id: str
    title: str
    car_make_name: str
    driver_name: str
    showroom_link: str
    thumb_url: str
    users: int
    bookmarks: int
    page_number: int
    raw: dict


@dataclass(frozen=True)
class DownloadOptions:
    detect_pages: bool
    skip_numbered: bool
    prefer_official: bool
    extract_tga: bool
    include_spec: bool
    skip_existing: bool


def safe_name(value: str, fallback: str = "paint") -> str:
    text = str(value or "").strip()
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    return text[:80] or fallback


def int_from_any(value: object, default: int = 0) -> int:
    try:
        return int(str(value or "").strip())
    except Exception:
        return default


def showroom_link_from_item(item: dict) -> str:
    title = str(item.get("title") or item.get("name") or "").strip()
    for key in ("slink", "showroom_link", "link", "url"):
        value = str(item.get(key) or "").strip()
        if "/showroom/view/" in value:
            return value
    scheme_id = str(item.get("id") or "").strip()
    if not scheme_id:
        return ""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
    return f"https://www.tradingpaints.com/showroom/view/{scheme_id}/{slug}" if slug else ""


class ShowroomClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": APP_USER_AGENT,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def _start_url(self, *, category: str, mid: int, slug: str) -> str:
        safe_category = str(category or "Road").strip() or "Road"
        safe_slug = str(slug or f"car-{mid}").strip() or f"car-{mid}"
        return f"https://www.tradingpaints.com/showroom/{safe_category}/{mid}/{safe_slug}"

    def fetch_page(self, *, mid: int, category: str, slug: str, page_index: int, timeout: float = 20.0) -> list[dict]:
        pos = max(0, int(page_index)) * SHOWROOM_PAGE_SIZE
        url = (
            f"https://www.tradingpaints.com/js/showroom.php?mid={int(mid)}&"
            f"{DEFAULT_SHOWROOM_PARAMS}&pos={pos}&ts={int(time.time() * 1000)}"
        )
        headers = {
            "Referer": self._start_url(category=category, mid=mid, slug=slug),
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        response = self.session.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        cars = ((payload.get("output") or {}).get("cars") or []) if isinstance(payload, dict) else []
        if not isinstance(cars, list):
            return []
        return [item for item in cars if isinstance(item, dict)]

    def detect_total_pages(
        self,
        *,
        mid: int,
        category: str,
        slug: str,
        max_pages: int,
        log: Callable[[str], None],
        cancel_event: threading.Event,
    ) -> int:
        page_limit = max(1, min(int(max_pages or SHOWROOM_MAX_PAGE_LIMIT), SHOWROOM_MAX_PAGE_LIMIT))
        cache: dict[int, bool] = {}

        def page_exists(index: int) -> bool:
            if cancel_event.is_set():
                raise RuntimeError("cancelled")
            if index in cache:
                return cache[index]
            batch = self.fetch_page(mid=mid, category=category, slug=slug, page_index=index)
            exists = bool(batch)
            cache[index] = exists
            return exists

        if not page_exists(0):
            return 0

        last_good = 0
        probe = 1
        while probe < page_limit and page_exists(probe):
            last_good = probe
            probe *= 2

        low = last_good + 1
        high = min(probe, page_limit - 1)
        while low <= high:
            mid_page = (low + high) // 2
            if page_exists(mid_page):
                last_good = mid_page
                low = mid_page + 1
            else:
                high = mid_page - 1

        total = last_good + 1
        log(f"Total detectado no Showroom: {total} pagina(s), limitado a {page_limit}.")
        return total


def normalize_paint(item: dict, page_number: int) -> ShowroomPaint | None:
    scheme_id = str(item.get("id") or "").strip()
    if not scheme_id:
        return None
    return ShowroomPaint(
        scheme_id=scheme_id,
        title=str(item.get("title") or "").strip() or f"scheme {scheme_id}",
        car_make_name=str(item.get("car_make_name") or "").strip(),
        driver_name=str(item.get("drivername") or "").strip(),
        showroom_link=showroom_link_from_item(item),
        thumb_url=str(item.get("pic") or "").strip(),
        users=int_from_any(item.get("users")),
        bookmarks=int_from_any(item.get("bookmarks")),
        page_number=int(page_number),
        raw=dict(item),
    )


def usable_showroom_item(item: dict, *, skip_numbered: bool, prefer_official: bool) -> bool:
    if skip_numbered and str(item.get("hasnumber") or "").strip().lower() in {"1", "true", "yes", "y", "on"}:
        return False
    if prefer_official and str(item.get("official") or "0").strip() != "1":
        return False
    return True


def collect_random_paints(
    *,
    client: ShowroomClient,
    mid: int,
    category: str,
    slug: str,
    count: int,
    max_pages: int,
    detect_total_pages: bool,
    skip_numbered: bool,
    prefer_official: bool,
    log: Callable[[str], None],
    cancel_event: threading.Event,
) -> list[ShowroomPaint]:
    page_limit = max(1, min(int(max_pages or 1), SHOWROOM_MAX_PAGE_LIMIT))
    if detect_total_pages:
        detected = client.detect_total_pages(
            mid=mid,
            category=category,
            slug=slug,
            max_pages=page_limit,
            log=log,
            cancel_event=cancel_event,
        )
        page_limit = max(1, detected)

    pages = list(range(page_limit))
    random.shuffle(pages)
    seen_ids: set[str] = set()
    paints: list[ShowroomPaint] = []

    for page_index in pages:
        if cancel_event.is_set():
            break
        log(f"Buscando pagina {page_index + 1}/{page_limit}...")
        try:
            batch = client.fetch_page(mid=mid, category=category, slug=slug, page_index=page_index)
        except Exception as exc:
            log(f"Falha ao buscar pagina {page_index + 1}: {exc}")
            continue

        added = 0
        for item in batch:
            if not usable_showroom_item(item, skip_numbered=skip_numbered, prefer_official=prefer_official):
                continue
            paint = normalize_paint(item, page_index + 1)
            if paint is None or paint.scheme_id in seen_ids:
                continue
            seen_ids.add(paint.scheme_id)
            paints.append(paint)
            added += 1
        log(f"Pagina {page_index + 1}: {added} pintura(s) candidata(s). Pool atual: {len(paints)}.")
        if len(paints) >= count:
            break

    if not paints:
        return []
    random.shuffle(paints)
    return paints[: max(1, int(count))]


def download_url(session: requests.Session, url: str, destination: Path, *, timeout: tuple[float, float] = (10, 90)) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(destination.name + ".tmp")
    temp_path.unlink(missing_ok=True)
    with session.get(url, stream=True, timeout=timeout) as response:
        if response.status_code in UNAVAILABLE_STATUS_CODES:
            return f"unavailable:{response.status_code}"
        response.raise_for_status()
        with temp_path.open("wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    out.write(chunk)
    temp_path.replace(destination)
    return "ok"


def extract_bz2(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(destination.name + ".tmp")
    temp_path.unlink(missing_ok=True)
    with source.open("rb") as raw, bz2.open(raw, "rb") as decompressor, temp_path.open("wb") as out:
        shutil.copyfileobj(decompressor, out)
    temp_path.replace(destination)


def download_paint_pack(
    *,
    client: ShowroomClient,
    paint: ShowroomPaint,
    output_dir: Path,
    extract_tga: bool,
    include_spec: bool,
    skip_existing: bool,
    log: Callable[[str], None],
    cancel_event: threading.Event,
) -> tuple[bool, str]:
    pack_name = f"{paint.scheme_id}_{safe_name(paint.title)}"
    pack_dir = output_dir / pack_name
    final_car = pack_dir / "car.tga"
    compressed_car = pack_dir / "car.tga.bz2"
    spec_file = pack_dir / "car_spec.mip"
    meta_file = pack_dir / "meta.json"

    existing_target = final_car if extract_tga else compressed_car
    if skip_existing and existing_target.exists():
        log(f"{paint.scheme_id}: ja existe, pulando.")
        return True, "skipped"

    if cancel_event.is_set():
        return False, "cancelled"

    pack_dir.mkdir(parents=True, exist_ok=True)
    car_url = SHOWROOM_COMPRESSED_URL.format(scheme_id=paint.scheme_id)
    log(f"{paint.scheme_id}: baixando {paint.title}...")
    status = download_url(client.session, car_url, compressed_car)
    if status != "ok":
        log(f"{paint.scheme_id}: car.tga.bz2 indisponivel ({status}).")
        return False, status

    if extract_tga:
        try:
            extract_bz2(compressed_car, final_car)
            compressed_car.unlink(missing_ok=True)
            log(f"{paint.scheme_id}: salvo car.tga.")
        except Exception as exc:
            log(f"{paint.scheme_id}: falha ao extrair .bz2: {exc}")
            return False, "extract_failed"
    else:
        log(f"{paint.scheme_id}: salvo car.tga.bz2.")

    spec_status = "disabled"
    if include_spec and not cancel_event.is_set():
        spec_url = SHOWROOM_MIP_URL.format(scheme_id=paint.scheme_id)
        try:
            spec_status = download_url(client.session, spec_url, spec_file)
            if spec_status == "ok":
                log(f"{paint.scheme_id}: salvo car_spec.mip.")
            else:
                log(f"{paint.scheme_id}: car_spec.mip indisponivel ({spec_status}).")
        except Exception as exc:
            spec_status = "failed"
            log(f"{paint.scheme_id}: falha no car_spec.mip: {exc}")

    meta = {
        "scheme_id": paint.scheme_id,
        "title": paint.title,
        "car_make_name": paint.car_make_name,
        "driver_name": paint.driver_name,
        "showroom_link": paint.showroom_link,
        "thumb_url": paint.thumb_url,
        "users": paint.users,
        "bookmarks": paint.bookmarks,
        "page_number": paint.page_number,
        "downloaded_at": time.time(),
        "car_url": car_url,
        "spec_status": spec_status,
        "raw": paint.raw,
    }
    meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return True, "downloaded"


class RandomShowroomApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("860x620")
        self.minsize(760, 520)
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.status_queue: queue.Queue[str] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()

        default_output = Path.cwd() / "nishizumi_paints_showroom_downloads"
        self.car_id_var = tk.StringVar(value="")
        self.category_var = tk.StringVar(value="Road")
        self.slug_var = tk.StringVar(value="")
        self.count_var = tk.StringVar(value="10")
        self.max_pages_var = tk.StringVar(value="20")
        self.output_var = tk.StringVar(value=str(default_output))
        self.detect_pages_var = tk.BooleanVar(value=True)
        self.skip_numbered_var = tk.BooleanVar(value=True)
        self.prefer_official_var = tk.BooleanVar(value=False)
        self.extract_tga_var = tk.BooleanVar(value=True)
        self.include_spec_var = tk.BooleanVar(value=False)
        self.skip_existing_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Pronto.")

        self._build_ui()
        self.after(100, self._drain_log_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        form = ttk.LabelFrame(root, text="Opcoes")
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="Trading Paints car ID (mid)").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(form, textvariable=self.car_id_var, width=16).grid(row=0, column=1, sticky="ew", padx=8, pady=6)

        ttk.Label(form, text="Quantidade").grid(row=0, column=2, sticky="w", padx=8, pady=6)
        ttk.Entry(form, textvariable=self.count_var, width=10).grid(row=0, column=3, sticky="ew", padx=8, pady=6)

        ttk.Label(form, text="Categoria").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        ttk.Combobox(form, textvariable=self.category_var, values=("Road", "Oval"), width=12).grid(
            row=1, column=1, sticky="ew", padx=8, pady=6
        )

        ttk.Label(form, text="Slug opcional").grid(row=1, column=2, sticky="w", padx=8, pady=6)
        ttk.Entry(form, textvariable=self.slug_var).grid(row=1, column=3, sticky="ew", padx=8, pady=6)

        ttk.Label(form, text="Max. paginas").grid(row=2, column=0, sticky="w", padx=8, pady=6)
        ttk.Entry(form, textvariable=self.max_pages_var, width=10).grid(row=2, column=1, sticky="ew", padx=8, pady=6)

        ttk.Label(form, text="Pasta de saida").grid(row=2, column=2, sticky="w", padx=8, pady=6)
        out_row = ttk.Frame(form)
        out_row.grid(row=2, column=3, sticky="ew", padx=8, pady=6)
        out_row.columnconfigure(0, weight=1)
        ttk.Entry(out_row, textvariable=self.output_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(out_row, text="Escolher", command=self._choose_output_dir).grid(row=0, column=1, padx=(8, 0))

        checks = ttk.Frame(form)
        checks.grid(row=3, column=0, columnspan=4, sticky="ew", padx=8, pady=(2, 8))
        ttk.Checkbutton(checks, text="Detectar total de paginas", variable=self.detect_pages_var).grid(
            row=0, column=0, sticky="w", padx=(0, 16)
        )
        ttk.Checkbutton(checks, text="Evitar custom number", variable=self.skip_numbered_var).grid(
            row=0, column=1, sticky="w", padx=(0, 16)
        )
        ttk.Checkbutton(checks, text="Somente oficiais", variable=self.prefer_official_var).grid(
            row=0, column=2, sticky="w", padx=(0, 16)
        )
        ttk.Checkbutton(checks, text="Extrair para .tga", variable=self.extract_tga_var).grid(
            row=1, column=0, sticky="w", padx=(0, 16)
        )
        ttk.Checkbutton(checks, text="Tentar car_spec.mip", variable=self.include_spec_var).grid(
            row=1, column=1, sticky="w", padx=(0, 16)
        )
        ttk.Checkbutton(checks, text="Pular existentes", variable=self.skip_existing_var).grid(
            row=1, column=2, sticky="w", padx=(0, 16)
        )

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, pady=(10, 6))
        ttk.Button(actions, text="Confirmar e baixar", command=self._start).pack(side=tk.LEFT)
        ttk.Button(actions, text="Cancelar", command=self._cancel).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(actions, textvariable=self.status_var).pack(side=tk.LEFT, padx=12)

        log_frame = ttk.LabelFrame(root, text="Log")
        log_frame.pack(fill=tk.BOTH, expand=True)
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=18, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _choose_output_dir(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_var.get() or str(Path.cwd()))
        if chosen:
            self.output_var.set(chosen)

    def _log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{stamp}] {message}")

    def _drain_log_queue(self) -> None:
        drained = False
        while True:
            try:
                status = self.status_queue.get_nowait()
            except queue.Empty:
                break
            self.status_var.set(status)
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.insert(tk.END, message + "\n")
            drained = True
        if drained:
            self.log_text.see(tk.END)
        self.after(100, self._drain_log_queue)

    def _parse_inputs(self) -> tuple[int, int, int, str, str, Path] | None:
        try:
            mid = int(self.car_id_var.get().strip())
            if mid <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror(APP_TITLE, "Digite um car ID numerico valido.")
            return None
        try:
            count = int(self.count_var.get().strip())
            if count <= 0:
                raise ValueError
        except Exception:
            messagebox.showerror(APP_TITLE, "Digite uma quantidade numerica valida.")
            return None
        try:
            max_pages = int(self.max_pages_var.get().strip())
            if max_pages <= 0:
                raise ValueError
            max_pages = min(max_pages, SHOWROOM_MAX_PAGE_LIMIT)
        except Exception:
            messagebox.showerror(APP_TITLE, "Digite um limite de paginas valido.")
            return None
        category = self.category_var.get().strip() or "Road"
        slug = self.slug_var.get().strip() or f"car-{mid}"
        output_dir = Path(self.output_var.get().strip() or ".").expanduser()
        return mid, count, max_pages, category, slug, output_dir

    def _start(self) -> None:
        if self.worker_thread is not None and self.worker_thread.is_alive():
            messagebox.showinfo(APP_TITLE, "Um download ja esta rodando.")
            return
        parsed = self._parse_inputs()
        if parsed is None:
            return
        mid, count, max_pages, category, slug, output_dir = parsed
        final_output = output_dir / f"car_{mid}"
        answer = messagebox.askyesno(
            APP_TITLE,
            (
                f"Baixar ate {count} pintura(s) aleatoria(s) do Showroom para o car ID {mid}?\n\n"
                f"Saida:\n{final_output}"
            ),
        )
        if not answer:
            return
        options = DownloadOptions(
            detect_pages=bool(self.detect_pages_var.get()),
            skip_numbered=bool(self.skip_numbered_var.get()),
            prefer_official=bool(self.prefer_official_var.get()),
            extract_tga=bool(self.extract_tga_var.get()),
            include_spec=bool(self.include_spec_var.get()),
            skip_existing=bool(self.skip_existing_var.get()),
        )
        self.cancel_event.clear()
        self.status_var.set("Rodando...")
        self._log("Inicio.")
        self.worker_thread = threading.Thread(
            target=self._run_download,
            args=(mid, count, max_pages, category, slug, final_output, options),
            daemon=True,
        )
        self.worker_thread.start()

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.status_var.set("Cancelando...")
        self._log("Cancelamento solicitado.")

    def _set_status_from_worker(self, value: str) -> None:
        self.status_queue.put(value)

    def _run_download(
        self,
        mid: int,
        count: int,
        max_pages: int,
        category: str,
        slug: str,
        output_dir: Path,
        options: DownloadOptions,
    ) -> None:
        downloaded = 0
        skipped = 0
        failed = 0
        had_error = False
        try:
            client = ShowroomClient()
            self._log(f"Car ID {mid}; categoria {category}; slug {slug}.")
            paints = collect_random_paints(
                client=client,
                mid=mid,
                category=category,
                slug=slug,
                count=count,
                max_pages=max_pages,
                detect_total_pages=options.detect_pages,
                skip_numbered=options.skip_numbered,
                prefer_official=options.prefer_official,
                log=self._log,
                cancel_event=self.cancel_event,
            )
            if not paints:
                self._log("Nenhuma pintura candidata encontrada.")
                return
            self._log(f"Selecionadas {len(paints)} pintura(s).")
            for index, paint in enumerate(paints, start=1):
                if self.cancel_event.is_set():
                    self._log("Parado pelo usuario.")
                    break
                self._log(f"[{index}/{len(paints)}] {paint.scheme_id} - {paint.title}")
                ok, status = download_paint_pack(
                    client=client,
                    paint=paint,
                    output_dir=output_dir,
                    extract_tga=options.extract_tga,
                    include_spec=options.include_spec,
                    skip_existing=options.skip_existing,
                    log=self._log,
                    cancel_event=self.cancel_event,
                )
                if ok and status == "skipped":
                    skipped += 1
                elif ok:
                    downloaded += 1
                else:
                    failed += 1
            self._log(f"Resumo: baixadas={downloaded}, existentes={skipped}, falhas={failed}.")
            self._log(f"Pasta: {output_dir}")
        except Exception as exc:
            had_error = True
            self._log(f"Erro: {exc}")
        finally:
            if self.cancel_event.is_set():
                self._set_status_from_worker("Cancelado.")
            elif had_error:
                self._set_status_from_worker("Erro.")
            else:
                self._set_status_from_worker("Concluido.")


def main() -> int:
    app = RandomShowroomApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
