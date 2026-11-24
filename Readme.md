# Release v1.3 — pnlk_snapshot

Инкрементальный бэкап папки на чистом Python. Скрипт сканирует папку запуска, сохраняет снимки состояния файлов и при повторных запусках упаковывает в ZIP только то, что изменилось.

## Возможности

- **Полный рекурсивный обход** папки запуска и всех вложенных подпапок. Служебные папки `.snapshots/` и `.git/` из обхода исключаются.
- **Снимок файлов** — для каждого файла собираются название, полный путь, дата изменения (в машиночитаемом и человекочитаемом виде), размер и SHA-256 hash. Всё сохраняется в JSON-снимок с полной датой в имени: `snapshot_YYYY-MM-DD_HH-MM-SS.json`.
- **Детект изменений** — при повторном запуске скрипт находит самый свежий предыдущий снимок в `.snapshots/` и сравнивает каждый файл по hash, размеру и дате изменения. Совпало полностью — файл не трогаем; отличается или появился впервые — помечается для архивации.
- **Инкрементальный архив** — изменённые и новые файлы упаковываются в ZIP с сохранением вложенности папок. Архив создаётся **на уровень выше** папки запуска, в имени — имя корневой папки и дата: `<имя_папки>_changed_files_YYYY-MM-DD_HH-MM-SS.zip`.
- **Первый запуск** — если предыдущий снимок не найден (или не читается), в архив упаковываются все файлы. Дальше работает инкрементальная логика.
- **Автоматическое разбиение на части** — если архив выходит за 800 МБ, файлы распределяются по нескольким архивам с суффиксами `_part01`, `_part02` и так далее. Одиночный файл, который сам больше лимита, отправляется в отдельный архив с предупреждением в консоль. Если все файлы уместились в один архив — суффикс части не добавляется.
- **Без изменений — без архива.** Если с прошлого запуска ничего не поменялось, архив не создаётся, но новый снимок всё равно сохраняется.
- **Аккуратное завершение** — глобальный обработчик ошибок, код возврата отличает успех, прерывание пользователем и сбой; окно консоли не закрывается до нажатия Enter.

## Формат снимка

```json
{
  "created": "2026-11-24 16:30:00",
  "root": "/path/to/folder",
  "files": {
    "docs/report.txt": {
      "name": "report.txt",
      "mtime": 1763987400.123,
      "mtime_str": "2026-11-24 15:30:00",
      "size": 10240,
      "hash": "a1b2c3..."
    }
  }
}
```

## Структура после запуска

```
родительская_папка/
├── корневая_папка/
│   ├── файлы и подпапки...
│   └── .snapshots/
│       ├── snapshot_2026-11-24_14-00-00.json
│       └── snapshot_2026-11-24_16-30-00.json
└── корневая_папка_changed_files_2026-11-24_16-30-00.zip   ← здесь, на уровень выше
```

## Требования и запуск

- Python 3.6+ — только стандартная библиотека, зависимостей нет.
- Кроссплатформенность: Windows, Linux, macOS (пути нормализуются в `/`).
- Запуск из отслеживаемой папки:

```bash
python "! pnlk_snapshot_v.1.3.py"
```

## Примечания

- Изменение даже одного байта меняет hash — файл попадёт в архив. Копирование файла без изменений, наоборот, не пометит его.
- Снимки и архивы предыдущих запусков не удаляются автоматически — при необходимости чистите `.snapshots/` и родительскую папку вручную.
- При недоступности файла (права, блокировка) скрипт не падает, а пропускает его с сообщением в stderr.

---



<img width="979" height="512" alt="изображение" src="https://github.com/user-attachments/assets/477f598c-4597-4a08-945a-f77576ab412e" />






---

# Release v1.3 — pnlk_snapshot

Incremental folder backup in pure Python. The script scans the folder it is run from, stores snapshots of file state, and on subsequent runs packs only the changed files into a ZIP archive.

## Features

- **Full recursive scan** of the working folder and all nested subfolders. Service directories `.snapshots/` and `.git/` are excluded from the scan.
- **File snapshot** — for every file the script records: name, relative path, modification date (both machine-readable and human-readable), size, and SHA-256 hash. Everything is saved to a JSON snapshot with a full timestamp in the filename: `snapshot_YYYY-MM-DD_HH-MM-SS.json`.
- **Change detection** — on every run the script picks the latest previous snapshot from `.snapshots/` and compares each file by hash, size, and modification time. If everything matches, the file is skipped; if the file is new or differs in any of these fields, it is queued for archiving.
- **Incremental ZIP archive** — changed and new files are packed into a ZIP preserving the original folder structure. The archive is created **one level above** the working folder and is named `<folder_name>_changed_files_YYYY-MM-DD_HH-MM-SS.zip`.
- **First run** — if no previous snapshot is found (or it cannot be read), all files are packed into the archive. After that the incremental logic takes over.
- **Automatic splitting into parts** — if an archive would exceed 800 MB, the files are distributed across several archives with `_part01`, `_part02` and so on suffixes. A single file larger than the limit goes into its own archive with a warning printed to stderr. If everything fits into one archive, no part suffix is added.
- **No changes — no archive.** If nothing has changed since the last run, no archive is created, but a new snapshot is still saved.
- **Graceful exit** — a global exception handler, distinct exit codes for success / user interrupt / failure, and a console window that stays open until Enter is pressed.

## Snapshot format

```json
{
  "created": "2026-11-24 16:30:00",
  "root": "/path/to/folder",
  "files": {
    "docs/report.txt": {
      "name": "report.txt",
      "mtime": 1763987400.123,
      "mtime_str": "2026-11-24 15:30:00",
      "size": 10240,
      "hash": "a1b2c3..."
    }
  }
}
```

## Resulting layout

```
parent_folder/
+-- working_folder/
|   +-- files and subfolders...
|   +-- .snapshots/
|       +-- snapshot_2026-11-24_14-00-00.json
|       +-- snapshot_2026-11-24_16-30-00.json
+-- working_folder_changed_files_2026-11-24_16-30-00.zip   <- one level above
```

## Requirements and usage

- Python 3.6+ — standard library only, no external dependencies.
- Cross-platform: Windows, Linux, macOS (paths are normalized to `/`).
- Run from the folder you want to track:

```bash
python "! pnlk_snapshot_v.1.3.py"
```

## Notes

- Changing even a single byte changes the hash, so the file will be archived. Copying a file without modifications will not mark it as changed.
- Snapshots and archives from previous runs are not removed automatically — clean up `.snapshots/` and the parent folder manually if needed.
- If a file cannot be accessed (permissions, lock), the script does not crash; it skips the file with a message on stderr.

---



**Full Changelog**: https://github.com/DenisAShmelev/pnlk_Snapshot_and_archive/commits/v.1.3
