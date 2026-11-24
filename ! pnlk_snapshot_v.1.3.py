#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт сканирует текущую папку (рекурсивно), сохраняет снимок файлов
(имя, дата изменения, размер, хэш) в файл-снимок в подпапке .snapshots/,
а при повторном запуске сравнивает текущее состояние с предыдущим
снимком и упаковывает в zip те файлы, которые были изменены/добавлены.

Особенности:
- При первом запуске (нет предыдущего снимка) в архив упаковываются ВСЕ файлы.
- Zip-архив создаётся в родительской папке (на уровень выше папки запуска).
- Имя архива: <имя_папки>_changed_files_<дата>.zip
- Если объём архива превышает 800 МБ, файлы разбиваются на несколько
  архивов по ≤ 800 МБ с суффиксом _partNN.

Использование:
    python snapshot.py
"""

import os
import sys
import json
import hashlib
import zipfile
import traceback
from datetime import datetime

# Подпапка для хранения снимков
SNAPSHOT_DIR = ".snapshots"

# Имя базового файла снимка (без даты)
SNAPSHOT_PREFIX = "snapshot"
SNAPSHOT_EXT = ".json"

# Имя базового zip-архива (без даты)
ARCHIVE_PREFIX = "changed_files"
ARCHIVE_EXT = ".zip"

# Размер блока чтения при подсчёте хэша
HASH_BLOCK = 1024 * 1024  # 1 МБ

# Лимит объёма одного архива: 800 МБ
ARCHIVE_LIMIT = 800 * 1024 * 1024  # 800 МБ в байтах

# Запас на заголовки zip и возможное сжатие — оставляем небольшой люфт,
# чтобы после закрытия zip итоговый размер гарантированно не превысил лимит.
ARCHIVE_SAFETY_MARGIN = 2 * 1024 * 1024  # 2 МБ


def pause_on_exit():
    """Останавливает окно консоли до нажатия Enter."""
    try:
        input("\nНажмите Enter для выхода...")
    except (EOFError, KeyboardInterrupt):
        pass


def now_stamp():
    """Возвращает строку с полной датой для имени файла."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def ensure_snapshot_dir(root):
    """Создаёт подпапку для снимков, если её нет. Возвращает путь."""
    path = os.path.join(root, SNAPSHOT_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def find_latest_snapshot(snapshot_dir):
    """Ищет в папке снимков самый свежий файл snapshot_*.json."""
    if not os.path.isdir(snapshot_dir):
        return None
    candidates = []
    for name in os.listdir(snapshot_dir):
        if name.startswith(SNAPSHOT_PREFIX + "_") and name.endswith(SNAPSHOT_EXT):
            full = os.path.join(snapshot_dir, name)
            if os.path.isfile(full):
                candidates.append(full)
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1]


def file_hash(path):
    """Считает SHA-256 хэш файла."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(HASH_BLOCK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def scan_folder(root):
    """
    Рекурсивно сканирует папку root, пропуская подпапку .snapshots.
    Возвращает словарь: относительный_путь -> {name, mtime, size, hash}.
    """
    result = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (SNAPSHOT_DIR, ".git")]
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            try:
                st = os.stat(full)
                rel = os.path.relpath(full, root).replace("\\", "/")
                result[rel] = {
                    "name": fname,
                    "mtime": st.st_mtime,
                    "mtime_str": datetime.fromtimestamp(st.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "size": st.st_size,
                    "hash": file_hash(full),
                }
            except (OSError, PermissionError) as e:
                print(f"[!] Не удалось обработать {full}: {e}", file=sys.stderr)
    return result


def compare_snapshots(old, new):
    """Сравнивает старый и новый снимки, возвращает изменённые/новые пути."""
    changed = []
    for rel, info in new.items():
        old_info = old.get(rel)
        if old_info is None:
            changed.append(rel)
            continue
        if (
            old_info.get("hash") != info.get("hash")
            or old_info.get("size") != info.get("size")
            or old_info.get("mtime") != info.get("mtime")
        ):
            changed.append(rel)
    return changed


def _zip_current_size(zip_path):
    """Возвращает текущий размер файла zip на диске (0, если файла нет)."""
    try:
        return os.path.getsize(zip_path)
    except OSError:
        return 0


def make_zip_parts(root, rel_paths, base_name, output_dir, limit=ARCHIVE_LIMIT):
    """
    Упаковывает файлы в один или несколько zip-архивов, каждый ≤ limit байт.

    Параметры:
        root       — корень, относительно которого берутся файлы;
        rel_paths  — список относительных путей (в порядке упаковки);
        base_name  — базовое имя архива без расширения;
        output_dir — папка для архивов;
        limit      — максимальный размер одного архива в байтах.

    Возвращает список созданных путей.

    Логика:
        - Открываем zip, пишем файлы.
        - После каждого файла проверяем размер на диске. Если он близок к лимиту
          (>= limit - safety_margin) И есть ещё файлы, которые надо записать,
          закрываем текущий архив и открываем следующий.
        - Если файл сам по себе больше лимита — он попадёт в архив один
          (zip всё равно не даст разбить один файл), с предупреждением.
        - Если по итогу получился ровно один архив и он ≤ limit, суффикс _partNN
          не добавляется.
    """
    if not rel_paths:
        return []

    # Проверяем, помещается ли всё в один архив (по сумме исходных размеров
    # — это верхняя оценка, т.к. сжатие только уменьшает; но zip-заголовки
    # добавляют немного, поэтому ориентируемся на лимит с запасом).
    total_size = 0
    for rel in rel_paths:
        full = os.path.join(root, rel)
        try:
            total_size += os.path.getsize(full)
        except OSError:
            pass

    # Если суммарный размер с большим запасом меньше лимита — пишем один архив
    # (обычно так и происходит при повторных запусках с малым числом изменений).
    if total_size + ARCHIVE_SAFETY_MARGIN < limit:
        zip_path = os.path.join(output_dir, base_name + ARCHIVE_EXT)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in rel_paths:
                full = os.path.join(root, rel)
                if os.path.isfile(full):
                    zf.write(full, arcname=rel.replace("\\", "/"))
        return [zip_path]

    # Иначе — многотомная упаковка по фактическому размеру после записи.
    created = []
    part = 1
    zf = None
    zip_path = None

    def _open_next():
        nonlocal zf, zip_path, part
        zip_path = os.path.join(output_dir, f"{base_name}_part{part:02d}{ARCHIVE_EXT}")
        zf = zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED)

    def _close_current():
        nonlocal zf, zip_path, part
        if zf is not None:
            zf.close()
            zf = None
            created.append(zip_path)
            part += 1

    try:
        _open_next()
        for idx, rel in enumerate(rel_paths):
            full = os.path.join(root, rel)
            if not os.path.isfile(full):
                continue

            file_size = os.path.getsize(full)
            # Если один файл больше лимита — предупреждаем, но пишем как есть
            # (в отдельный архив, чтобы не портить остальные).
            if file_size + ARCHIVE_SAFETY_MARGIN >= limit:
                # Закрываем текущий (если в нём что-то уже есть) и пишем
                # большой файл в отдельный архив.
                if zf is not None:
                    # проверяем, пуст ли текущий архив — если пуст, можно писать сюда
                    # но проще: если в текущем архиве уже что-то есть, закрыть
                    # (отслеживаем через локальный флаг)
                    pass
                print(
                    f"[!] Файл {rel} ({file_size} байт) сам превышает лимит "
                    f"{limit} байт — будет помещён в отдельный архив.",
                    file=sys.stderr,
                )
                _close_current()
                _open_next()
                zf.write(full, arcname=rel.replace("\\", "/"))
                _close_current()
                continue

            # Если текущий архив уже открыт и запись файла превысит лимит —
            # закрываем его и открываем новый.
            current_size = _zip_current_size(zip_path) if zip_path else 0
            if current_size and (current_size + file_size + ARCHIVE_SAFETY_MARGIN >= limit):
                _close_current()
                _open_next()

            # Если zf закрыт (после большого файла) — открываем
            if zf is None:
                _open_next()

            zf.write(full, arcname=rel.replace("\\", "/"))
    finally:
        _close_current()

    # Постпроверка: если получился один архив — переименуем в base_name.zip
    if len(created) == 1:
        single = created[0]
        target = os.path.join(output_dir, base_name + ARCHIVE_EXT)
        if single != target:
            try:
                os.replace(single, target)
                created = [target]
            except OSError:
                pass

    return created


def main():
    root = os.getcwd()
    root = os.path.abspath(root)
    parent = os.path.dirname(root)
    folder_name = os.path.basename(root.rstrip(os.sep)) or "root"

    print(f"[i] Рабочая папка: {root}")
    print(f"[i] Папка для архивов: {parent}")
    print(f"[i] Лимит объёма одного архива: {ARCHIVE_LIMIT // (1024 * 1024)} МБ")

    snapshot_dir = ensure_snapshot_dir(root)

    old_snapshot_path = find_latest_snapshot(snapshot_dir)
    old_snapshot = {}
    first_run = False
    if old_snapshot_path:
        print(f"[i] Найден предыдущий снимок: {os.path.relpath(old_snapshot_path, root)}")
        try:
            with open(old_snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                old_snapshot = data.get("files", {})
        except (OSError, json.JSONDecodeError) as e:
            print(f"[!] Не удалось прочитать снимок: {e}", file=sys.stderr)
            old_snapshot = {}
            first_run = True
    else:
        print("[i] Предыдущий снимок не найден — это первый запуск.")
        first_run = True

    print("[i] Сканирование файлов...")
    new_snapshot = scan_folder(root)
    print(f"[i] Обработано файлов: {len(new_snapshot)}")

    if first_run or not old_snapshot:
        files_to_zip = list(new_snapshot.keys())
        if files_to_zip:
            print(f"[i] Первый запуск — в архив будут упакованы все файлы ({len(files_to_zip)} шт.)")
        else:
            print("[i] Файлов для архивации нет.")
    else:
        files_to_zip = compare_snapshots(old_snapshot, new_snapshot)
        if files_to_zip:
            print(f"[i] Изменённых/новых файлов: {len(files_to_zip)}")
        else:
            print("[i] Изменений не обнаружено — архив не создаётся.")

    if files_to_zip:
        base_name = f"{folder_name}_{ARCHIVE_PREFIX}_{now_stamp()}"
        for rel in files_to_zip:
            print(f"    + {rel}")
        archives = make_zip_parts(root, files_to_zip, base_name, parent)
        if len(archives) == 1:
            print(f"[+] Создан архив: {archives[0]}")
        else:
            print(f"[+] Создано {len(archives)} архивов:")
            for p in archives:
                size_mb = os.path.getsize(p) / (1024 * 1024)
                print(f"    - {p}  ({size_mb:.1f} МБ)")

    snapshot_name = f"{SNAPSHOT_PREFIX}_{now_stamp()}{SNAPSHOT_EXT}"
    snapshot_path = os.path.join(snapshot_dir, snapshot_name)
    payload = {
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "root": root,
        "files": new_snapshot,
    }
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[+] Сохранён снимок: {os.path.relpath(snapshot_path, root)}")


def _global_excepthook(exc_type, exc_value, exc_tb):
    """Глобальный обработчик необработанных исключений."""
    print("\n[!] Необработанная ошибка:", file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)


if __name__ == "__main__":
    sys.excepthook = _global_excepthook
    exit_code = 0
    try:
        main()
        print("\n[✓] Скрипт успешно завершён.")
    except KeyboardInterrupt:
        print("\n[!] Прервано пользователем.", file=sys.stderr)
        exit_code = 130
    except Exception:
        print("\n[!] Во время выполнения произошла ошибка:", file=sys.stderr)
        traceback.print_exc()
        exit_code = 1
    finally:
        pause_on_exit()
    sys.exit(exit_code)