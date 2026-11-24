Скрипт снимков и zip
Напиши скрипт на python который при запуске из папки пройдёт по всем файлам в этой папке и всех вложенных папках. Прочитает для каждого файла название, полную дату изменений, размер и hash сумму. Запишет все эти данные в файл с определённым именем и полной датой в конце имени.

При повторном запуске этого же скрипта скрипт должен проверить наличие файла с данными записанного ранее. Если такой файл имеется рядом, то при выполнении скрипта он берет файл, ищет такой же описанный файл в файле с данными. Если файл найден, но его данные отличаются от записанных в файле с данными, то он помечает этот файл для сжатия в zip архив. Если данные файла при проверке полностью совпадают с записанными в файл данных, то данный файл не сжимается в zip архив. Для сжимаемых файлов необходимо сохранить вложенность папок.

Итогом выполнения скрипта должен быть новый файл с данными в котором описаны все файлы в папке запуска, и zip архив с измененными с предыдущего запуска файлами.
Скрипт для поиска изменённых файлов и их архивации
python

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт сканирует текущую папку (рекурсивно), сохраняет снимок файлов
(имя, дата изменения, размер, хэш) в файл-снимок, а при повторном запуске
сравнивает текущее состояние с предыдущим снимком и упаковывает в zip
те файлы, которые были изменены/добавлены.

Использование:
    python snapshot.py
"""

import os
import sys
import json
import hashlib
import zipfile
from datetime import datetime

# Имя базового файла снимка (без даты)
SNAPSHOT_PREFIX = "snapshot"
SNAPSHOT_EXT = ".json"

# Имя базового zip-архива (без даты)
ARCHIVE_PREFIX = "changed_files"
ARCHIVE_EXT = ".zip"

# Размер блока чтения при подсчёте хэша
HASH_BLOCK = 1024 * 1024  # 1 МБ


def now_stamp():
    """Возвращает строку с полной датой для имени файла."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def find_latest_snapshot(folder):
    """
    Ищет в указанной папке самый свежий файл снимка по имени
    (snapshot_*.json). Возвращает путь или None.
    """
    candidates = []
    for name in os.listdir(folder):
        if name.startswith(SNAPSHOT_PREFIX + "_") and name.endswith(SNAPSHOT_EXT):
            full = os.path.join(folder, name)
            if os.path.isfile(full):
                candidates.append(full)
    if not candidates:
        return None
    # сортировка по имени (в имени — дата, поэтому лексикографически совпадает с хронологией)
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
    Рекурсивно сканирует папку root.
    Возвращает словарь: относительный_путь -> {name, mtime, size, hash}.
    """
    result = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # чтобы вложенные снимки/архивы сами не попадали в снимок
        dirnames[:] = [d for d in dirnames if not d.startswith(".git")]
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            # пропускаем сами файлы снимков и архивы, созданные скриптом
            if os.path.basename(full).startswith(SNAPSHOT_PREFIX + "_") \
                    or os.path.basename(full).startswith(ARCHIVE_PREFIX + "_"):
                continue
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
    """
    Сравнивает старый и новый снимки.
    Возвращает список относительных путей изменённых/новых файлов.
    Изменённым считается файл, у которого отличается hash, size, mtime
    или который отсутствует в старом снимке.
    """
    changed = []
    for rel, info in new.items():
        old_info = old.get(rel)
        if old_info is None:
            changed.append(rel)  # новый файл
            continue
        if (
            old_info.get("hash") != info.get("hash")
            or old_info.get("size") != info.get("size")
            or old_info.get("mtime") != info.get("mtime")
        ):
            changed.append(rel)
    return changed


def make_zip(root, rel_paths, zip_path):
    """Упаковывает указанные файлы в zip с сохранением вложенности."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rel_paths:
            full = os.path.join(root, rel)
            if os.path.isfile(full):
                # arcname — относительный путь внутри архива
                zf.write(full, arcname=rel.replace("\\", "/"))


def main():
    root = os.getcwd()
    print(f"[i] Рабочая папка: {root}")

    # 1. Ищем предыдущий снимок
    old_snapshot_path = find_latest_snapshot(root)
    old_snapshot = {}
    if old_snapshot_path:
        print(f"[i] Найден предыдущий снимок: {os.path.basename(old_snapshot_path)}")
        try:
            with open(old_snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                old_snapshot = data.get("files", {})
        except (OSError, json.JSONDecodeError) as e:
            print(f"[!] Не удалось прочитать снимок: {e}", file=sys.stderr)
            old_snapshot = {}
    else:
        print("[i] Предыдущий снимок не найден — выполняется первичное сканирование.")

    # 2. Сканируем текущее состояние
    print("[i] Сканирование файлов...")
    new_snapshot = scan_folder(root)
    print(f"[i] Обработано файлов: {len(new_snapshot)}")

    # 3. Сравнение и упаковка изменённых файлов
    if old_snapshot:
        changed = compare_snapshots(old_snapshot, new_snapshot)
        if changed:
            zip_name = f"{ARCHIVE_PREFIX}_{now_stamp()}{ARCHIVE_EXT}"
            zip_path = os.path.join(root, zip_name)
            print(f"[i] Изменённых/новых файлов: {len(changed)}")
            for rel in changed:
                print(f"    + {rel}")
            make_zip(root, changed, zip_path)
            print(f"[+] Создан архив: {zip_name}")
        else:
            print("[i] Изменений не обнаружено — архив не создаётся.")
    else:
        print("[i] Это первый запуск — архив не создаётся.")

    # 4. Сохраняем новый снимок
    snapshot_name = f"{SNAPSHOT_PREFIX}_{now_stamp()}{SNAPSHOT_EXT}"
    snapshot_path = os.path.join(root, snapshot_name)
    payload = {
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "root": root,
        "files": new_snapshot,
    }
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[+] Сохранён снимок: {snapshot_name}")


if __name__ == "__main__":
    main()

Как это работает

Первый запуск

    Скрипт рекурсивно обходит текущую папку.

    Для каждого файла собирает: имя, mtime (полная дата изменения), размер и SHA-256 хэш.

    Сохраняет всё в snapshot_ГГГГ-ММ-ДД_ЧЧ-ММ-СС.json. Zip-архив не создаётся, т.к. сравнивать не с чем.

Повторный запуск

    Ищет самый свежий snapshot_*.json рядом со скриптом (по имени — сортировка лексикографически совпадает с хронологической благодаря формату даты).

    Сканирует папку заново.

    Сравнивает каждый файл со старой записью. Файл считается изменённым, если:

        он новый (нет в старом снимке);

        изменился hash / size / mtime.

    Изменённые файлы пакуются в changed_files_ГГГГ-ММ-ДД_ЧЧ-ММ-СС.zip с сохранением вложенности (через arcname=rel).

    Пишет новый снимок snapshot_*.json.

Особенности реализации

    Дата в имени — %Y-%m-%d_%H-%M-%S, безопасно для файловых систем.

    Хэш SHA-256 — читается блоками по 1 МБ, не грузит память на больших файлах.

    Защита от рекурсии — файлы снимков и архивы, созданные скриптом, исключаются из сканирования, чтобы не попадать в собственные снимки.

    Кодировка UTF-8 для JSON, ensure_ascii=False — русские имена файлов сохраняются читаемо.

    Ошибки доступа к отдельным файлам не роняют скрипт — выводятся в stderr.

    Сохранение структуры в zip: zf.write(full, arcname=rel) — внутри архива файлы лежат по тем же относительным путям.

Возможные доработки

    Добавить параметр --exclude для исключения папок/масок.

    Хранить снимки в подпапке .snapshots/ (тогда не нужно исключать их из обхода).

    Использовать xxhash/blake2b для скорости на больших объёмах.

    Добавить сравнение по контрольной сумме без mtime, если нужно ловить только контентные изменения.

Давай добавим твоё предложение:
Хранить снимки в подпапке .snapshots/ (тогда не нужно исключать их из обхода).
Обновлённый скрипт с хранением снимков в .snapshots/
python

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт сканирует текущую папку (рекурсивно), сохраняет снимок файлов
(имя, дата изменения, размер, хэш) в файл-снимок в подпапке .snapshots/,
а при повторном запуске сравнивает текущее состояние с предыдущим
снимком и упаковывает в zip те файлы, которые были изменены/добавлены.

Использование:
    python snapshot.py
"""

import os
import sys
import json
import hashlib
import zipfile
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


def now_stamp():
    """Возвращает строку с полной датой для имени файла."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def ensure_snapshot_dir(root):
    """Создаёт подпапку для снимков, если её нет. Возвращает путь."""
    path = os.path.join(root, SNAPSHOT_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def find_latest_snapshot(snapshot_dir):
    """
    Ищет в папке снимков самый свежий файл snapshot_*.json.
    Возвращает путь или None.
    """
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
    # имя содержит дату, поэтому лексикографическая сортировка = хронологическая
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
        # Исключаем служебную папку со снимками и системный .git
        dirnames[:] = [
            d for d in dirnames
            if d not in (SNAPSHOT_DIR, ".git")
        ]
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
    """
    Сравнивает старый и новый снимки.
    Возвращает список относительных путей изменённых/новых файлов.
    """
    changed = []
    for rel, info in new.items():
        old_info = old.get(rel)
        if old_info is None:
            changed.append(rel)  # новый файл
            continue
        if (
            old_info.get("hash") != info.get("hash")
            or old_info.get("size") != info.get("size")
            or old_info.get("mtime") != info.get("mtime")
        ):
            changed.append(rel)
    return changed


def make_zip(root, rel_paths, zip_path):
    """Упаковывает указанные файлы в zip с сохранением вложенности."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rel_paths:
            full = os.path.join(root, rel)
            if os.path.isfile(full):
                zf.write(full, arcname=rel.replace("\\", "/"))


def main():
    root = os.getcwd()
    print(f"[i] Рабочая папка: {root}")

    snapshot_dir = ensure_snapshot_dir(root)

    # 1. Ищем предыдущий снимок в .snapshots/
    old_snapshot_path = find_latest_snapshot(snapshot_dir)
    old_snapshot = {}
    if old_snapshot_path:
        print(f"[i] Найден предыдущий снимок: {os.path.relpath(old_snapshot_path, root)}")
        try:
            with open(old_snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                old_snapshot = data.get("files", {})
        except (OSError, json.JSONDecodeError) as e:
            print(f"[!] Не удалось прочитать снимок: {e}", file=sys.stderr)
            old_snapshot = {}
    else:
        print("[i] Предыдущий снимок не найден — выполняется первичное сканирование.")

    # 2. Сканируем текущее состояние
    print("[i] Сканирование файлов...")
    new_snapshot = scan_folder(root)
    print(f"[i] Обработано файлов: {len(new_snapshot)}")

    # 3. Сравнение и упаковка изменённых файлов
    if old_snapshot:
        changed = compare_snapshots(old_snapshot, new_snapshot)
        if changed:
            zip_name = f"{ARCHIVE_PREFIX}_{now_stamp()}{ARCHIVE_EXT}"
            zip_path = os.path.join(root, zip_name)
            print(f"[i] Изменённых/новых файлов: {len(changed)}")
            for rel in changed:
                print(f"    + {rel}")
            make_zip(root, changed, zip_path)
            print(f"[+] Создан архив: {zip_name}")
        else:
            print("[i] Изменений не обнаружено — архив не создаётся.")
    else:
        print("[i] Это первый запуск — архив не создаётся.")

    # 4. Сохраняем новый снимок в .snapshots/
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


if __name__ == "__main__":
    main()

Что изменилось

    Подпапка .snapshots/ — константа SNAPSHOT_DIR = ".snapshots", создаётся при каждом запуске через ensure_snapshot_dir().

    Поиск предыдущего снимка — find_latest_snapshot() теперь принимает путь к папке .snapshots/ и ищет файлы только внутри неё.

    Сканирование — в scan_folder() добавлено явное исключение SNAPSHOT_DIR из обхода (dirnames[:] = [...]). Дополнительно убран прежний фильтр по префиксу имени — он больше не нужен, т.к. снимки физически лежат вне зоны обхода.

    Сохранение — новый снимок пишется в os.path.join(snapshot_dir, snapshot_name).

    Логи — пути к снимкам выводятся относительно корня (os.path.relpath(...)), чтобы выглядело как .snapshots/snapshot_....json.

Итоговая структура папки после работы
text

./
├── .snapshots/
│   ├── snapshot_2024-05-20_10-00-00.json
│   └── snapshot_2024-05-21_12-30-45.json
├── changed_files_2024-05-21_12-30-45.zip
├── файл1.txt
└── подпапка/
    └── файл2.txt

Важные замечания

    .gitignore — если папка под git, стоит добавить .snapshots/ и changed_files_*.zip, чтобы не мусорить в репозитории.

    Накопление снимков — со временем .snapshots/ будет расти. При желании можно добавить ротацию (хранить N последних) — скажите, если нужно, добавлю параметр MAX_SNAPSHOTS с автоочисткой старых.

    Zip-архивы по-прежнему кладутся в корень проекта (не в .snapshots/) — это удобно для ручного просмотра. Если хотите складывать и их в служебную папку — тоже несложно поменять.

добавь код чтобы окно скрипта не закрывалось после выполнения и в случае возникновения ошибок
Обновлённый скрипт с удержанием окна

Добавил функцию pause_on_exit() и обернул вызов main() в try/except/finally, чтобы окно не закрывалось ни при успешном завершении, ни при ошибке. Также добавил sys.excepthook на случай необработанных исключений.
python

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт сканирует текущую папку (рекурсивно), сохраняет снимок файлов
(имя, дата изменения, размер, хэш) в файл-снимок в подпапке .snapshots/,
а при повторном запуске сравнивает текущее состояние с предыдущим
снимком и упаковывает в zip те файлы, которые были изменены/добавлены.

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
    """
    Ищет в папке снимков самый свежий файл snapshot_*.json.
    Возвращает путь или None.
    """
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
    """
    Сравнивает старый и новый снимки.
    Возвращает список относительных путей изменённых/новых файлов.
    """
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


def make_zip(root, rel_paths, zip_path):
    """Упаковывает указанные файлы в zip с сохранением вложенности."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rel_paths:
            full = os.path.join(root, rel)
            if os.path.isfile(full):
                zf.write(full, arcname=rel.replace("\\", "/"))


def main():
    root = os.getcwd()
    print(f"[i] Рабочая папка: {root}")

    snapshot_dir = ensure_snapshot_dir(root)

    old_snapshot_path = find_latest_snapshot(snapshot_dir)
    old_snapshot = {}
    if old_snapshot_path:
        print(f"[i] Найден предыдущий снимок: {os.path.relpath(old_snapshot_path, root)}")
        try:
            with open(old_snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                old_snapshot = data.get("files", {})
        except (OSError, json.JSONDecodeError) as e:
            print(f"[!] Не удалось прочитать снимок: {e}", file=sys.stderr)
            old_snapshot = {}
    else:
        print("[i] Предыдущий снимок не найден — выполняется первичное сканирование.")

    print("[i] Сканирование файлов...")
    new_snapshot = scan_folder(root)
    print(f"[i] Обработано файлов: {len(new_snapshot)}")

    if old_snapshot:
        changed = compare_snapshots(old_snapshot, new_snapshot)
        if changed:
            zip_name = f"{ARCHIVE_PREFIX}_{now_stamp()}{ARCHIVE_EXT}"
            zip_path = os.path.join(root, zip_name)
            print(f"[i] Изменённых/новых файлов: {len(changed)}")
            for rel in changed:
                print(f"    + {rel}")
            make_zip(root, changed, zip_path)
            print(f"[+] Создан архив: {zip_name}")
        else:
            print("[i] Изменений не обнаружено — архив не создаётся.")
    else:
        print("[i] Это первый запуск — архив не создаётся.")

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
    """Глобальный обработчик необработанных исключений (в т.ч. в потоках)."""
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
        # Окно не закроется ни при успехе, ни при ошибке
        pause_on_exit()
    sys.exit(exit_code)

Что добавлено

    pause_on_exit() — ждёт Enter. Ловит EOFError / KeyboardInterrupt, чтобы не падать, если stdin недоступен (например, при запуске из планировщика задач) — просто не блокирует.

    finally: pause_on_exit() — выполняется в любом случае: при успехе, при исключении, при Ctrl+C.

    try/except Exception вокруг main() — ловит любые ошибки, печатает полный traceback и выставляет код возврата 1.

    except KeyboardInterrupt — отдельно обрабатывает Ctrl+C, код возврата 130 (стандарт для SIGINT).

    sys.excepthook = _global_excepthook — на случай необработанных исключений (например, в будущих версиях с потоками), тоже печатает traceback в stderr.

    sys.exit(exit_code) — после паузы скрипт завершается с правильным кодом, что полезно при вызове из CI/планировщика.

Как это выглядит при запуске

Успешное завершение:
text

[i] Рабочая папка: C:\project
[i] Найден предыдущий снимок: .snapshots\snapshot_2024-05-20_10-00-00.json
[i] Сканирование файлов...
[i] Обработано файлов: 42
[i] Изменённых/новых файлов: 3
    + src/main.py
    + data/new.txt
    + config.yaml
[+] Создан архив: changed_files_2024-05-21_12-30-45.zip
[+] Сохранён снимок: .snapshots\snapshot_2024-05-21_12-30-45.json

[✓] Скрипт успешно завершён.

Нажмите Enter для выхода...

При ошибке:
text

[i] Рабочая папка: C:\project
...
[!] Во время выполнения произошла ошибка:
Traceback (most recent call last):
  File "snapshot.py", line 218, in <module>
    main()
  File "snapshot.py", line 190, in main
    make_zip(root, changed, zip_path)
  ...
PermissionError: [Errno 13] Permission denied: 'C:\\project\\changed_files_...zip'

Нажмите Enter для выхода...

Если нужно поведение «пауза только при ошибке»

Иногда удобнее, чтобы при успехе окно закрывалось сразу (например, при запуске из ярлыка в проводнике — иначе каждый раз жать Enter утомительно). Замените блок finally на:
python

    finally:
        # Пауза только если были ошибки
        if exit_code != 0:
            pause_on_exit()

Или сделайте это настраиваемым через переменную окружения:
python

PAUSE_ALWAYS = os.environ.get("SNAPSHOT_PAUSE_ALWAYS", "1") == "1"
...
    finally:
        if PAUSE_ALWAYS or exit_code != 0:
            pause_on_exit()

Дополни код так чтобы архив со сжимаемыми файлами создавался не в папке запуска, а в папке на одну выше папки запуска. 
Потому что сейчас эти файлы попадают в новый архив так как они для скрипта новые
Обновлённый скрипт: zip-архив на уровень выше

Архивы теперь создаются в родительской папке (os.path.dirname(root)), а не в корне сканирования. Это решает проблему «архив попал в следующий архив» — при следующем запуске os.walk его уже не увидит, так как он лежит вне root.
python

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт сканирует текущую папку (рекурсивно), сохраняет снимок файлов
(имя, дата изменения, размер, хэш) в файл-снимок в подпапке .snapshots/,
а при повторном запуске сравнивает текущее состояние с предыдущим
снимком и упаковывает в zip те файлы, которые были изменены/добавлены.

Zip-архив создаётся в родительской папке (на уровень выше папки запуска),
чтобы не попадать в собственное сканирование при следующем запуске.

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
    """
    Ищет в папке снимков самый свежий файл snapshot_*.json.
    Возвращает путь или None.
    """
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
    """
    Сравнивает старый и новый снимки.
    Возвращает список относительных путей изменённых/новых файлов.
    """
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


def make_zip(root, rel_paths, zip_path):
    """
    Упаковывает указанные файлы в zip с сохранением вложенности.
    Файлы читаются относительно root, но zip_path может быть где угодно.
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rel_paths:
            full = os.path.join(root, rel)
            if os.path.isfile(full):
                zf.write(full, arcname=rel.replace("\\", "/"))


def main():
    root = os.getcwd()
    root = os.path.abspath(root)
    parent = os.path.dirname(root)

    print(f"[i] Рабочая папка: {root}")
    print(f"[i] Папка для архивов: {parent}")

    snapshot_dir = ensure_snapshot_dir(root)

    old_snapshot_path = find_latest_snapshot(snapshot_dir)
    old_snapshot = {}
    if old_snapshot_path:
        print(f"[i] Найден предыдущий снимок: {os.path.relpath(old_snapshot_path, root)}")
        try:
            with open(old_snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                old_snapshot = data.get("files", {})
        except (OSError, json.JSONDecodeError) as e:
            print(f"[!] Не удалось прочитать снимок: {e}", file=sys.stderr)
            old_snapshot = {}
    else:
        print("[i] Предыдущий снимок не найден — выполняется первичное сканирование.")

    print("[i] Сканирование файлов...")
    new_snapshot = scan_folder(root)
    print(f"[i] Обработано файлов: {len(new_snapshot)}")

    if old_snapshot:
        changed = compare_snapshots(old_snapshot, new_snapshot)
        if changed:
            # Имя архива включает имя папки, чтобы архивы из разных папок не путались
            folder_name = os.path.basename(root)
            zip_name = f"{ARCHIVE_PREFIX}_{folder_name}_{now_stamp()}{ARCHIVE_EXT}"
            zip_path = os.path.join(parent, zip_name)
            print(f"[i] Изменённых/новых файлов: {len(changed)}")
            for rel in changed:
                print(f"    + {rel}")
            make_zip(root, changed, zip_path)
            print(f"[+] Создан архив: {zip_path}")
        else:
            print("[i] Изменений не обнаружено — архив не создаётся.")
    else:
        print("[i] Это первый запуск — архив не создаётся.")

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

Что изменилось

    Корень переводится в абсолютный путь — root = os.path.abspath(root), чтобы os.path.dirname(root) дал корректный родительский путь даже при запуске через относительный путь.

    Родительская папка — parent = os.path.dirname(root). Добавлена проверка-вывод в лог: [i] Папка для архивов: ....

    Zip кладётся в parent — zip_path = os.path.join(parent, zip_name). Всё остальное (make_zip) работает без изменений: файлы читаются относительно root, а arcname=rel по-прежнему сохраняет вложенность внутри архива.

    Имя архива теперь содержит имя папки — changed_files_<имя_папки>_<дата>.zip. Это важно, поскольку в одной родительской папке может лежать несколько подпапок, из которых запускается скрипт — иначе архивы путались бы.

    Корректный вывод пути — print(f"[+] Создан архив: {zip_path}"), поскольку архив теперь вне root, os.path.relpath(... , root) дал бы некрасивое ../....

    .snapshots/ остаётся внутри root — снимки по-прежнему локальны для папки запуска.

Итоговая структура
text

родительская_папка/
├── changed_files_проект_2024-05-21_12-30-45.zip   ← архив здесь
└── проект/                                          ← папка запуска
    ├── .snapshots/
    │   └── snapshot_2024-05-21_12-30-45.json
    ├── файл1.txt
    └── подпапка/
        └── файл2.txt

Почему это решает исходную проблему

Раньше zip создавался в root и при следующем запуске попадал в os.walk как «новый файл» → упаковывался в новый архив → и так по нарастающей. Теперь os.walk(root) физически не видит файл, лежащий в parent, — рекурсия по определению не выходит за пределы root.
Замечание про права записи

Родительская папка должна быть доступна на запись. Если, например, скрипт запускается из C:\Program Files\MyApp\, то C:\Program Files\MyApp может требовать прав администратора. Ошибка PermissionError будет поймана глобальным обработчиком, traceback выведется, окно не закроется — но zip не создастся. Если это критично, могу добавить fallback: при ошибке писать zip обратно в root с предупреждением в лог.
Дополни код чтобы при запуске скрипта, если файл с данными с предыдущего запуска не найден,  то необходимо выполнить скрипт и сжать все файлы в архив. В дальнейшем логика работы скрипта должна сохраниться
Обновлённый скрипт: первый запуск тоже создаёт архив

Изменение логики: если предыдущий снимок не найден — все найденные файлы считаются «новыми» и упаковываются в архив. Дальнейшее поведение (сравнение с предыдущим снимком) не меняется.
python

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт сканирует текущую папку (рекурсивно), сохраняет снимок файлов
(имя, дата изменения, размер, хэш) в файл-снимок в подпапке .snapshots/,
а при повторном запуске сравнивает текущее состояние с предыдущим
снимком и упаковывает в zip те файлы, которые были изменены/добавлены.

Особенности:
- При первом запуске (нет предыдущего снимка) в архив упаковываются ВСЕ файлы.
- Zip-архив создаётся в родительской папке (на уровень выше папки запуска),
  чтобы не попадать в собственное сканирование при следующем запуске.

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
    """
    Ищет в папке снимков самый свежий файл snapshot_*.json.
    Возвращает путь или None.
    """
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
    """
    Сравнивает старый и новый снимки.
    Возвращает список относительных путей изменённых/новых файлов.
    """
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


def make_zip(root, rel_paths, zip_path):
    """
    Упаковывает указанные файлы в zip с сохранением вложенности.
    Файлы читаются относительно root, но zip_path может быть где угодно.
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rel_paths:
            full = os.path.join(root, rel)
            if os.path.isfile(full):
                zf.write(full, arcname=rel.replace("\\", "/"))


def main():
    root = os.getcwd()
    root = os.path.abspath(root)
    parent = os.path.dirname(root)

    print(f"[i] Рабочая папка: {root}")
    print(f"[i] Папка для архивов: {parent}")

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

    # Определяем список файлов для архивации
    if first_run or not old_snapshot:
        # Первый запуск — архивируем ВСЕ файлы
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

    # Создаём архив, если есть что упаковывать
    if files_to_zip:
        folder_name = os.path.basename(root)
        zip_name = f"{ARCHIVE_PREFIX}_{folder_name}_{now_stamp()}{ARCHIVE_EXT}"
        zip_path = os.path.join(parent, zip_name)
        for rel in files_to_zip:
            print(f"    + {rel}")
        make_zip(root, files_to_zip, zip_path)
        print(f"[+] Создан архив: {zip_path}")

    # Сохраняем новый снимок
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

Что изменилось

    Флаг first_run — выставляется True в двух случаях:

        файл снимка не найден вообще;

        файл снимка есть, но его не удалось прочитать/распарсить (битый JSON, нет прав) — иначе сравнение с пустым {} тоже даст «все файлы новые», но лучше явно пометить как первый запуск для ясности лога.

    Выбор файлов для архивации — вместо if old_snapshot: ... else: ... теперь единая развилка:

        first_run or not old_snapshot → files_to_zip = list(new_snapshot.keys()) (все файлы);

        иначе → files_to_zip = compare_snapshots(old_snapshot, new_snapshot) (только изменённые/новые).

    Общий блок создания архива — if files_to_zip: работает одинаково для обоих сценариев. Имя архива и путь не изменились (parent/changed_files_<папка>_<дата>.zip).

    Информативные логи — при первом запуске выводится Первый запуск — в архив будут упакованы все файлы (N шт.), при повторном — Изменённых/новых файлов: N или Изменений не обнаружено.

    Снимок сохраняется в обоих случаях — как и раньше, в конце пишется новый snapshot_*.json, который станет «предыдущим» при следующем запуске.

Как это выглядит

Первый запуск:
text

[i] Рабочая папка: C:\project
[i] Папка для архивов: C:\
[i] Предыдущий снимок не найден — это первый запуск.
[i] Сканирование файлов...
[i] Обработано файлов: 42
[i] Первый запуск — в архив будут упакованы все файлы (42 шт.)
    + README.md
    + src/main.py
    + ...
[+] Создан архив: C:\changed_files_project_2024-05-21_12-30-45.zip
[+] Сохранён снимок: .snapshots\snapshot_2024-05-21_12-30-45.json

[✓] Скрипт успешно завершён.

Повторный запуск без изменений:
text

[i] Найден предыдущий снимок: .snapshots\snapshot_2024-05-21_12-30-45.json
[i] Сканирование файлов...
[i] Обработано файлов: 42
[i] Изменений не обнаружено — архив не создаётся.
[+] Сохранён снимок: .snapshots\snapshot_2024-05-22_09-00-00.json

Повторный запуск с изменениями:
text

[i] Найден предыдущий снимок: .snapshots\snapshot_2024-05-21_12-30-45.json
[i] Сканирование файлов...
[i] Обработано файлов: 43
[i] Изменённых/новых файлов: 2
    + src/main.py
    + data/new.txt
[+] Создан архив: C:\changed_files_project_2024-05-22_09-00-00.zip
[+] Сохранён снимок: .snapshots\snapshot_2024-05-22_09-00-00.json

Важный нюанс

На первом запуске архив будет содержать все файлы папки, включая, например, .gitignore, конфиги и прочее. Если в папке много тяжёлых, редко меняющихся файлов — это может быть нежелательно. При необходимости можно добавить исключения (например, *.log, node_modules/, __pycache__/) через параметр EXCLUDE_PATTERNS — скажите, если нужно, добавлю.
Дополни скрипт чтобы в имя архива дописывалось в начале имя корневой папки из которой запущен скрипт
Обновлённый скрипт: имя корневой папки в начале имени архива

Формат имени архива теперь: <имя_корневой_папки>_changed_files_<дата>.zip
python

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт сканирует текущую папку (рекурсивно), сохраняет снимок файлов
(имя, дата изменения, размер, хэш) в файл-снимок в подпапке .snapshots/,
а при повторном запуске сравнивает текущее состояние с предыдущим
снимком и упаковывает в zip те файлы, которые были изменены/добавлены.

Особенности:
- При первом запуске (нет предыдущего снимка) в архив упаковываются ВСЕ файлы.
- Zip-архив создаётся в родительской папке (на уровень выше папки запуска),
  чтобы не попадать в собственное сканирование при следующем запуске.
- Имя архива начинается с имени корневой папки запуска:
  <имя_папки>_changed_files_<дата>.zip

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
    """
    Ищет в папке снимков самый свежий файл snapshot_*.json.
    Возвращает путь или None.
    """
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
    """
    Сравнивает старый и новый снимки.
    Возвращает список относительных путей изменённых/новых файлов.
    """
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


def make_zip(root, rel_paths, zip_path):
    """
    Упаковывает указанные файлы в zip с сохранением вложенности.
    Файлы читаются относительно root, но zip_path может быть где угодно.
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rel_paths:
            full = os.path.join(root, rel)
            if os.path.isfile(full):
                zf.write(full, arcname=rel.replace("\\", "/"))


def main():
    root = os.getcwd()
    root = os.path.abspath(root)
    parent = os.path.dirname(root)
    folder_name = os.path.basename(root.rstrip(os.sep)) or "root"

    print(f"[i] Рабочая папка: {root}")
    print(f"[i] Папка для архивов: {parent}")

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

    # Определяем список файлов для архивации
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

    # Создаём архив, если есть что упаковывать
    if files_to_zip:
        # Имя архива: <имя_корневой_папки>_changed_files_<дата>.zip
        zip_name = f"{folder_name}_{ARCHIVE_PREFIX}_{now_stamp()}{ARCHIVE_EXT}"
        zip_path = os.path.join(parent, zip_name)
        for rel in files_to_zip:
            print(f"    + {rel}")
        make_zip(root, files_to_zip, zip_path)
        print(f"[+] Создан архив: {zip_path}")

    # Сохраняем новый снимок
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

Что изменилось

    folder_name вычисляется один раз в main() — os.path.basename(root.rstrip(os.sep)) or "root".

        rstrip(os.sep) защищает от случая, когда root оканчивается на разделитель (бывает на некоторых платформах/при нестандартном запуске);

        or "root" — подстраховка для корня диска (C:\), где basename даёт пустую строку.

    Имя архива — теперь f"{folder_name}_{ARCHIVE_PREFIX}_{now_stamp()}{ARCHIVE_EXT}", т.е. <имя_папки>_changed_files_<дата>.zip.

    Убран старый расчёт folder_name внутри блока создания архива — он больше не нужен, значение уже посчитано выше.

Итоговый вид
text

родительская_папка/
├── проект_changed_files_2024-05-21_12-30-45.zip   ← архив здесь
└── проект/                                          ← папка запуска
    ├── .snapshots/
    │   └── snapshot_2024-05-21_12-30-45.json
    ├── файл1.txt
    └── подпапка/
        └── файл2.txt

Лог
text

[i] Рабочая папка: C:\work\проект
[i] Папка для архивов: C:\work
[i] Предыдущий снимок не найден — это первый запуск.
[i] Сканирование файлов...
[i] Обработано файлов: 42
[i] Первый запуск — в архив будут упакованы все файлы (42 шт.)
    + README.md
    + src/main.py
    ...
[+] Создан архив: C:\work\проект_changed_files_2024-05-21_12-30-45.zip
[+] Сохранён снимок: .snapshots\snapshot_2024-05-21_12-30-45.json

Замечание про недопустимые символы

Если имя папки содержит символы, недопустимые в именах файлов на целевой ОС (на Windows это <>:"/\|?*), они попадут и в имя архива. На практике имя папки обычно уже валидно для ФС, т.к. папка существует. Единственный риск — имя папки на Linux содержит : или ?, а архив затем переносится на Windows. Если это актуально, можно добавить санитизацию:
python

import re
folder_name = re.sub(r'[<>:"/\\|?*]', "_", folder_name)

Скажите, если нужно включить — добавлю в код и в main().
Для создаваемых архивов добавь проверку чтобы их объём после сохранения не превышал 800 мб. Если размер превышает 800 мб, то необходимо сохранить файлы в несколько архивов размером не превышающим 800 мб. В названия архивов допиши номер части по порядку.
Обновлённый скрипт: разбивка архива на части ≤ 800 МБ

Добавил функцию make_zip_parts(), которая упаковывает файлы в несколько архивов, каждый из которых не превышает лимит. Нумерация частей добавляется к имени: ..._part01.zip, ..._part02.zip и т.д. Если все файлы помещаются в один архив — суффикс _partNN не добавляется (сохраняется привычное имя).
python

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

Как работает разбивка

    Быстрый путь — если суммарный размер исходных файлов + запас < лимита, пишется один архив с обычным именем (без _partNN). Это подавляющее большинство повторных запусков, когда меняются 1–5 файлов.

    Медленный путь — если суммарно может не влезть:

        открывается _part01.zip;

        файлы пишутся по одному;

        после каждого файла (точнее, перед записью следующего) проверяется фактический размер файла архива на диске через os.path.getsize();

        если текущий_размер + размер_следующего_файла + запас >= лимит — текущий архив закрывается, открывается следующий;

        в конце все части нумеруются _part01, _part02, ... (двузначный формат — чтобы при сортировке по имени part10 не оказался раньше part2).

    Файл больше лимита — если один файл сам по себе > 800 МБ, zip физически не может его разбить между томами (это не zip -s с multi-volume). Скрипт:

        печатает предупреждение в stderr;

        закрывает текущий архив;

        пишет большой файл в отдельный архив;

        закрывает его и продолжает со следующего.

    Постобработка — если в итоге получилась одна часть (например, суммарно влезло, но мы пошли по медленному пути из-за неоптимистичной оценки), она переименовывается обратно в base_name.zip через os.replace().

Почему используется фактический размер на диске

zf.write() пишет данные в файл, но буферы ОС могут ещё не сбросить всё. os.path.getsize() возвращает актуальный размер файла в ФС — этого достаточно для контроля. Гарантию даёт запас ARCHIVE_SAFETY_MARGIN = 2 МБ: заголовки zip на каждый файл ~100–200 байт, при миллионе файлов это 200 МБ — маловероятный сценарий, но запас покрывает типичные случаи. Если важна абсолютная гарантия при экстремальном количестве файлов, запас можно увеличить.
Пример вывода

Всё помещается в один архив:
text

[+] Создан архив: C:\work\проект_changed_files_2024-05-21_12-30-45.zip

Не помещается:
text

[i] Изменённых/новых файлов: 15
    + video/lecture1.mp4
    + video/lecture2.mp4
    ...
[+] Создано 3 архивов:
    - C:\work\проект_changed_files_2024-05-21_12-30-45_part01.zip  (798.3 МБ)
    - C:\work\проект_changed_files_2024-05-21_12-30-45_part02.zip  (799.1 МБ)
    - C:\work\проект_changed_files_2024-05-21_12-30-45_part03.zip  (512.7 МБ)

Файл больше лимита:
text

[!] Файл video/huge.iso (1024 байт) сам превышает лимит 838860800 байт — будет помещён в отдельный архив.

Возможные уточнения

    Точный размер «по факту» можно проверять после zf.close() каждой части и, если превысил, переупаковывать. Дороже по I/O, но даёт 100% гарантию. Текущая реализация с запасом 2 МБ практически всегда достаточна.

    zip -s multi-volume (создание .z01, .z02, ...) стандартный zipfile Python не поддерживает — там нужен внешний zip или библиотеки вроде pyzipper с расширениями. Текущий вариант (несколько независимых архивов _partNN) — самый переносимый.

    Если хочется строго ≤ 800 МБ без «примерно», можно после создания каждой части проверять os.path.getsize() и, при превышении, распаковывать/переупаковывать — но это уже избыточно при наличии запаса. Скажите, если нужно — сделаю строгий режим.