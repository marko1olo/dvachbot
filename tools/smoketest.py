from __future__ import annotations
import contextlib
#!/usr/bin/env python3
"""
Дымовой прогон: поднимается ли бот на ЧИСТОЙ базе и корректно ли он
отказывается стартовать, когда стартовать нельзя.

Запуск:
    python tools/smoketest.py            # все этапы
    python tools/smoketest.py --list
    python tools/smoketest.py schema     # только выбранные

Код возврата 1 при первом провале. Боевую БД не трогает: всё делается во
временном каталоге, куда переопределяются DB_NAME в common.config,
common.db_pool и common.database. Сеть не задействована - все этапы
заканчиваются до создания ботов.

Зачем это отдельно от tools/selfcheck.py: selfcheck читает код, а этот
прогон его ИСПОЛНЯЕТ. Разница не теоретическая - именно так нашлось, что
фатальный отказ старта завершался кодом 0 и супервизор считал запуск
успешным. Ни один статический анализ такого не видит.

Важная тонкость про этап refusal: main.py запускается как ОТДЕЛЬНЫЙ
процесс, а не импортом. Иначе не отработает настоящий блок __main__,
именно в котором и был дефект. Плюс прямой вызов load_state() проходит
мимо finally в main(), где graceful_shutdown закрывает пул БД, - поток
aiosqlite недемонический, и интерпретатор ждёт его вечно. Такое
зависание было бы артефактом теста, а не находкой.
"""

import argparse
import os
import subprocess
import sys
import tempfile
import textwrap
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ожидаемая нижняя граница. Не точные числа, а защита от обвала: если
# обработчиков внезапно стало вдвое меньше, значит регистрация поехала.
MIN_MESSAGE_HANDLERS = 100
MIN_CALLBACK_HANDLERS = 20
# Типы апдейтов, без которых бот заведомо неполон. message_reaction здесь
# не для красоты: он уже терялся, когда декоратор достался чужой функции.
REQUIRED_UPDATE_TYPES = ("message", "callback_query", "message_reaction")
# Колонки, которых не хватало на чистой БД и из-за которых падала
# регистрация медиа и вся экономика.
REQUIRED_COLUMNS = {
    "Users": ("active_items", "cursed_until", "custom_prefix",
              "prefix_expires_at", "reaction_reward_counter"),
    "FileRegistry": ("tags",),
}
BOOT_TIMEOUT_SEC = 180.0


class Failure(Exception):
    pass


def _run_child(code: str, dbp: str, cwd: str, timeout: float):
    """Исполняет код в отдельном процессе с переопределённым путём к БД."""
    shim = os.path.join(cwd, "sitecustomize.py")
    with open(shim, "w", encoding="utf-8") as fh:
        fh.write(textwrap.dedent(f"""
            import sys
            sys.path.insert(0, r"{ROOT}")
            import common.config as cfg; cfg.DB_NAME = r"{dbp}"
            import common.db_pool as pool; pool.DB_NAME = r"{dbp}"
            import common.database as D; D.DB_NAME = r"{dbp}"
        """))
    script = os.path.join(cwd, "child.py")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(code)
    env = dict(os.environ)
    env["PYTHONPATH"] = cwd
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, script], cwd=cwd, env=env, timeout=timeout,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


# --------------------------------------------------------------------------
def stage_import(ctx):
    """main.py импортируется без ошибок."""
    code = textwrap.dedent("""
        import time, sys
        t = time.perf_counter()
        import main
        print(f"IMPORT_SECONDS={time.perf_counter() - t:.1f}")
        print("IMPORT_OK")
    """)
    r = _run_child(code, ctx["db"], ctx["cwd"], BOOT_TIMEOUT_SEC)
    if "IMPORT_OK" not in r.stdout:
        raise Failure(f"main.py не импортируется:\n{(r.stderr or r.stdout)[-900:]}")
    secs = next((l.split("=")[1] for l in r.stdout.splitlines()
                 if l.startswith("IMPORT_SECONDS")), "?")
    return f"импорт main.py за {secs} с"


def stage_schema(ctx):
    """initialize_database на чистой БД создаёт всё, что нужно коду."""
    need = repr(REQUIRED_COLUMNS)
    code = textwrap.dedent(f"""
        import asyncio, sqlite3, io, contextlib, sys
        import common.database as D, common.db_pool as pool
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(D.initialize_database())
        with contextlib.closing(sqlite3.connect(D.DB_NAME)) as con:
        missing = []
        for table, cols in {need}.items():
            have = [r[1] for r in con.execute(f"PRAGMA table_info({{table}})")]
            if not have:
                missing.append(f"{{table}} (таблицы нет)")
                continue
            for c in cols:
                if c not in have:
                    missing.append(f"{{table}}.{{c}}")
        n_tables = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        n_idx = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index'").fetchone()[0]
        con.close()
        print(f"MISSING={{'|'.join(missing)}}")
        print(f"TABLES={{n_tables}} INDEXES={{n_idx}}")
        print("SCHEMA_OK")
    """)
    r = _run_child(code, ctx["db"], ctx["cwd"], BOOT_TIMEOUT_SEC)
    if "SCHEMA_OK" not in r.stdout:
        raise Failure(f"схема не поднимается:\n{(r.stderr or r.stdout)[-900:]}")
    missing = next((l.split("=", 1)[1] for l in r.stdout.splitlines()
                    if l.startswith("MISSING")), "")
    if missing:
        raise Failure(f"на чистой БД нет колонок: {missing}")
    counts = next((l for l in r.stdout.splitlines() if l.startswith("TABLES")), "")
    return f"схема поднята, {counts.lower().replace('tables=', 'таблиц ').replace('indexes=', 'индексов ')}"


def stage_handlers(ctx):
    """Обработчики зарегистрированы, и зарегистрированы ПРАВИЛЬНЫЕ функции.

    Считать количество регистраций недостаточно, и это выяснилось на живом
    примере: когда декоратор @dp.message_reaction() достался хелперу
    _send_notification_quietly, счётчик обработчиков и список запрашиваемых
    типов апдейтов остались прежними - обработчик-то зарегистрирован, просто
    не тот. Поэтому смотрим сигнатуру КАЖДОГО зарегистрированного вызова: у
    обработчика aiogram первый параметр всегда объект события.
    """
    code = textwrap.dedent(f"""
        import io, contextlib, inspect
        with contextlib.redirect_stdout(io.StringIO()):
            import main
        EXPECT = {{
            "message": ("message", "msg", "event"),
            "callback_query": ("callback", "call", "query", "cb", "event"),
            "message_reaction": ("reaction", "event", "update"),
            "inline_query": ("query", "inline_query", "event"),
        }}
        counts = {{}}
        bad = []
        for obs_name, names in EXPECT.items():
            obs = getattr(main.dp, obs_name, None)
            if obs is None:
                continue
            counts[obs_name] = len(obs.handlers)
            for h in obs.handlers:
                cb = h.callback
                params = list(inspect.signature(cb).parameters)
                if not params:
                    bad.append(f"{{obs_name}}:{{cb.__name__}}(без параметров)")
                elif not any(n in params[0] for n in names):
                    bad.append(f"{{obs_name}}:{{cb.__name__}}(первый параметр {{params[0]!r}})")
        types_ = sorted(main.dp.resolve_used_update_types())
        print("COUNTS=" + ",".join(f"{{k}}:{{v}}" for k, v in counts.items()))
        print("TYPES=" + ",".join(types_))
        print("MISSING_TYPES=" + ",".join(t for t in {REQUIRED_UPDATE_TYPES!r} if t not in types_))
        print("BAD=" + "|".join(bad))
        print("HANDLERS_OK")
    """)
    r = _run_child(code, ctx["db"], ctx["cwd"], BOOT_TIMEOUT_SEC)
    if "HANDLERS_OK" not in r.stdout:
        raise Failure(f"не удалось перечислить обработчики:\n{(r.stderr or r.stdout)[-900:]}")
    out = {l.split("=", 1)[0]: l.split("=", 1)[1]
           for l in r.stdout.splitlines() if "=" in l}
    miss = [x for x in out.get("MISSING_TYPES", "").split(",") if x]
    if miss:
        raise Failure(f"бот не запросит у Telegram типы апдейтов: {miss}")
    bad = [x for x in out.get("BAD", "").split("|") if x]
    if bad:
        raise Failure(
            f"зарегистрированы функции с сигнатурой не под событие: {bad}. "
            f"Обычная причина - код вставлен МЕЖДУ декоратором и его обработчиком"
        )
    counts = dict(p.split(":") for p in out["COUNTS"].split(",") if ":" in p)
    m = int(counts.get("message", 0))
    c = int(counts.get("callback_query", 0))
    rc = int(counts.get("message_reaction", 0))
    if m < MIN_MESSAGE_HANDLERS or c < MIN_CALLBACK_HANDLERS or rc < 1:
        raise Failure(
            f"подозрительно мало обработчиков: message={m}, callback={c}, reaction={rc} "
            f"(ожидалось не меньше {MIN_MESSAGE_HANDLERS}/{MIN_CALLBACK_HANDLERS}/1)"
        )
    return (f"обработчиков {out['COUNTS']}, сигнатуры сходятся; "
            f"апдейты {out['TYPES']}")


def stage_refusal(ctx):
    """На незаполненной БД бот отказывается стартовать - и делает это ПРАВИЛЬНО.

    Правильно значит три вещи: не зависнуть, закрыть соединение с БД и
    вернуть НЕнулевой код, чтобы супервизор увидел аварию.
    """
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py")],
            cwd=ctx["cwd"], env={**os.environ, "PYTHONPATH": ctx["cwd"],
                                 "PYTHONIOENCODING": "utf-8"},
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=BOOT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        raise Failure(
            f"main.py не завершился за {BOOT_TIMEOUT_SEC:.0f} с на пустой БД - зависание"
        )
    el = time.perf_counter() - t0
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        raise Failure(
            "фатальный отказ старта вернул код 0: супервизор сочтёт запуск успешным "
            "и не перезапустит бота"
        )
    if "корректно закрыто" not in out:
        raise Failure("при отказе старта соединение с БД не было закрыто штатно")
    return f"отказ корректен: код {r.returncode}, БД закрыта, {el:.1f} с"


STAGES = {
    "import": ("main.py импортируется", stage_import),
    "schema": ("схема на чистой БД", stage_schema),
    "handlers": ("обработчики и типы апдейтов", stage_handlers),
    "refusal": ("отказ старта на пустой БД", stage_refusal),
}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stages", nargs="*", help="какие этапы прогнать (по умолчанию все)")
    ap.add_argument("--list", action="store_true", help="перечислить этапы и выйти")
    args = ap.parse_args(argv)

    if args.list:
        for key, (title, _) in STAGES.items():
            print(f"  {key:<10} {title}")
        return 0

    selected = args.stages or list(STAGES)
    unknown = [s for s in selected if s not in STAGES]
    if unknown:
        print(f"неизвестные этапы: {unknown}; доступны: {list(STAGES)}")
        return 2

    work = tempfile.mkdtemp(prefix="dvachbot-smoke-")
    ctx = {"cwd": work, "db": os.path.join(work, "fresh.db")}
    failed = 0
    try:
        for key in selected:
            title, fn = STAGES[key]
            t = time.perf_counter()
            try:
                detail = fn(ctx)
                print(f"[OK  ] {key:<10} {title}: {detail}  ({time.perf_counter() - t:.1f} с)")
            except Failure as exc:
                failed += 1
                print(f"[ПРОВ] {key:<10} {title}")
                print(f"         {exc}")
            except Exception as exc:  # noqa: BLE001 - хотим видеть любую поломку
                failed += 1
                print(f"[ОШИБ] {key:<10} {title}: {type(exc).__name__}: {exc}")
    finally:
        import shutil

        shutil.rmtree(work, ignore_errors=True)

    print(f"\nпровалов: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
