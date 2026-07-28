#!/usr/bin/env python3
"""
Статические проверки, каждая из которых уже нашла в этом проекте
работающий баг. Держим их как постоянный сторож, а не как разовый разбор.

Запуск:
    python tools/selfcheck.py            # все проверки
    python tools/selfcheck.py --fast     # только по AST, без поднятия БД
    python tools/selfcheck.py --list     # перечислить проверки
    python tools/selfcheck.py dup sql    # только выбранные

Код возврата 1, если что-то найдено. Ничего не правит и не пишет в проект;
для проверок sql и growth поднимает временную БД настоящим
initialize_database во временном каталоге и удаляет её за собой.

Подключение к pre-commit, если понадобится, - решение владельца
репозитория: хуки здесь настроены глобально через core.hooksPath, то есть
один каталог на ВСЕ проекты, и падающая или медленная проверка
заблокировала бы коммиты везде. Для такого сценария есть --fast.

Почему именно эти семь: все они выросли из реальных поломок.
  dup      - /stats и /shoot не работали НИКОГДА: победившее определение
             из трёх было сломанным
  arity    - вызов с параметром, которого нет в сигнатуре: TypeError
  sql      - на чистой БД не хватало шести колонок, ломалась регистрация
             медиа и вся экономика
  invars   - очереди между сайтом и ботом умирали навсегда, перейдя
             лимит переменных SQLite
  dictkeys - 1096 вариантов замен молча терялись на повторяющихся ключах
  growth   - таблица росла без границ, потому что её забыли в списке
             очистки сирот
  handlers - команда, зарегистрированная дважды, работает только первая
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import contextlib
import io
import os
import re
import sqlite3
import sys
import tempfile
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = ("tests", "scratch", "archive", ".git", "tools")

# Файлы, которые крутятся в бою. Остальное проверяем мягче: сломанный
# одноразовый скрипт не стоит красного билда.
LIVE = (
    "main.py",
    "common/database.py",
    "common/db_pool.py",
    "common/bot_pool.py",
    "common/task_manager.py",
    "periodic_publisher.py",
    "economy_extension.py",
    "site_tgach/main.py",
    "site_tgach/tagging_worker.py",
)


def _py_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".py"):
                p = os.path.relpath(os.path.join(dirpath, fn), ROOT).replace(os.sep, "/")
                if not any(p.startswith(s + "/") for s in SKIP_DIRS):
                    yield p


_PARSE_CACHE: dict[str, tuple] = {}


def _parse(path):
    """Разбор с кэшем: main.py весит мегабайт, а его читают шесть проверок."""
    if path not in _PARSE_CACHE:
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
                src = fh.read()
            _PARSE_CACHE[path] = (src, ast.parse(src))
        except (OSError, SyntaxError):
            _PARSE_CACHE[path] = (None, None)
    return _PARSE_CACHE[path]


# --------------------------------------------------------------------------
def check_dup(report):
    """Затенённые определения на уровне модуля.

    Побеждает ПОСЛЕДНЕЕ, и именно оно оказывалось сломанным в /stats и
    /shoot. Декораторы-маршруты пропускаем: у них своя семантика (у
    @app.get побеждает первый зарегистрированный, а не последний).
    """
    for path in LIVE:
        src, tree = _parse(path)
        if tree is None:
            continue
        seen = defaultdict(list)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                decs = [ast.unparse(d) for d in node.decorator_list]
                if any(re.match(r"(app|router)\.", d) or "overload" in d for d in decs):
                    continue
                seen[node.name].append(node.lineno)
        for name, lines in seen.items():
            if len(lines) > 1:
                report(
                    path, lines[-1],
                    f"{name} объявлен {len(lines)} раза (строки {lines}); "
                    f"работает только последнее",
                )


# --------------------------------------------------------------------------
def check_arity(report):
    """Вызовы, не подходящие под сигнатуру функции или dataclass в том же файле."""
    skip_dec = ("overload", "singledispatch", "app.", "dp.", "router.", "api.")
    for path in _py_files():
        src, tree = _parse(path)
        if tree is None:
            continue
        defs = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(any(s in ast.unparse(d) for s in skip_dec) for d in node.decorator_list):
                    continue
                a = node.args
                pos = a.posonlyargs + a.args
                defs[node.name] = dict(
                    minpos=len(pos) - len(a.defaults),
                    maxpos=None if a.vararg else len(pos),
                    names={x.arg for x in a.args} | {x.arg for x in a.kwonlyargs},
                    anykw=a.kwarg is not None,
                    where=node.lineno,
                )
            elif isinstance(node, ast.ClassDef) and any(
                "dataclass" in ast.unparse(d) for d in node.decorator_list
            ):
                flds = [s for s in node.body if isinstance(s, ast.AnnAssign)]
                defs[node.name] = dict(
                    minpos=sum(1 for s in flds if s.value is None),
                    maxpos=len(flds),
                    names={s.target.id for s in flds},
                    anykw=False,
                    where=node.lineno,
                )
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            d = defs.get(node.func.id)
            if d is None:
                continue
            if any(isinstance(a, ast.Starred) for a in node.args):
                continue
            if any(k.arg is None for k in node.keywords):
                continue
            npos = len(node.args)
            kws = {k.arg for k in node.keywords}
            if d["maxpos"] is not None and npos > d["maxpos"]:
                report(path, node.lineno,
                       f"{node.func.id}(): позиционных {npos} при максимуме {d['maxpos']} "
                       f"(определение строка {d['where']})")
            elif npos + len(kws) < d["minpos"]:
                report(path, node.lineno,
                       f"{node.func.id}(): аргументов {npos + len(kws)} при "
                       f"обязательных {d['minpos']} (определение строка {d['where']})")
            elif not d["anykw"] and (kws - d["names"]):
                report(path, node.lineno,
                       f"{node.func.id}(): нет таких параметров "
                       f"{sorted(kws - d['names'])} (определение строка {d['where']})")


# --------------------------------------------------------------------------
def _fresh_db():
    """Поднимает пустую БД настоящим initialize_database во временном каталоге."""
    tmp = tempfile.mkdtemp()
    dbp = os.path.join(tmp, "selfcheck.db")
    sys.path.insert(0, ROOT)
    import common.config as cfg
    import common.db_pool as pool
    import common.database as database

    cfg.DB_NAME = dbp
    pool.DB_NAME = dbp
    database.DB_NAME = dbp
    with contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(database.initialize_database())
    return tmp, dbp


_SQL_START = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE)\b", re.I)
# Требуем настоящую форму запроса. Без этого под проверку попадали строки
# интерфейса вроде "Select View Mode" из common/locales.py: начинаются со
# слова SELECT, но SQL не являются.
_SQL_SHAPE = re.compile(r"\b(FROM|INTO|SET|VALUES)\b", re.I)
# Таблицы, которые модуль создаёт сам перед обращением, и подстановка имени
# таблицы в f-строку — то и другое даёт ложное срабатывание.
_SQL_IGNORE = re.compile(r'FROM\s+"?\?|VoiceTranscriptions', re.I)


def _sql_literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            str(v.value) if isinstance(v, ast.Constant) else "?" for v in node.values
        )
    return None


def check_sql(report):
    """Каждый статический SQL обязан компилироваться против ЧИСТОЙ схемы.

    EXPLAIN готовит запрос, не выполняя его, и ловит несуществующие колонки
    и таблицы. Именно так нашлись шесть колонок, которых не было в схеме:
    на боевой БД они остались от прежних версий, а новое развёртывание
    падало.
    """
    tmp, dbp = _fresh_db()
    con = sqlite3.connect(dbp)
    try:
        seen = set()
        for path in _py_files():
            if "Dubsite" in path:
                continue
            src, tree = _parse(path)
            if tree is None:
                continue
            for node in ast.walk(tree):
                s = _sql_literal(node)
                if not s or not _SQL_START.match(s) or not _SQL_SHAPE.search(s):
                    continue
                if _SQL_IGNORE.search(s):
                    continue
                key = " ".join(s.split())
                if key in seen:
                    continue
                seen.add(key)
                try:
                    con.execute("EXPLAIN " + s)
                except sqlite3.OperationalError as exc:
                    msg = str(exc)
                    if "no such column" in msg or "no such table" in msg or "has no column" in msg:
                        report(path, getattr(node, "lineno", 0), f"{msg}: {key[:70]}")
                except Exception:
                    pass
    finally:
        con.close()
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
def check_invars(report):
    """IN (...) без разбиения на пачки там, где длину задают накопленные данные.

    Предел SQLite SQLITE_LIMIT_VARIABLE_NUMBER равен 32766. Обработчики
    ошибок в проекте ретраят только locked/busy, поэтому такое падение не
    восстанавливается: четыре очереди между сайтом и ботом умирали навсегда.
    Ловим только функции-разгребатели очередей, где размер не ограничен
    кодом; разовые выборки по списку из запроса пользователя не в счёт.
    """
    queueish = re.compile(r"queue|pending|unsent|backlog", re.I)
    for path in LIVE:
        src, tree = _parse(path)
        if tree is None:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not queueish.search(fn.name):
                continue
            body = "\n".join(src.splitlines()[fn.lineno - 1 : fn.end_lineno])
            if "IN (" not in body and "IN ({" not in body:
                continue
            builds = re.findall(r"','\.join\('\?' for _ in (\w+)\)", body)
            for var in builds:
                # безопасно, если переменная приходит из нарезки на пачки
                if re.search(rf"for {var} in iter_sql_chunks|{var}\s*=\s*\w+\[", body):
                    continue
                if "iter_sql_chunks" in body:
                    continue
                report(path, fn.lineno,
                       f"{fn.name}(): IN (...) по '{var}' без разбиения на пачки; "
                       f"предел SQLite 32766 параметров")


# --------------------------------------------------------------------------
def check_dictkeys(report):
    """Повторяющиеся ключи словаря с РАЗНЫМИ значениями.

    В литерале побеждает последний, ранние значения просто не существуют.
    Так молча терялись 1096 вариантов замен в режимах.
    """
    for path in _py_files():
        src, tree = _parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            seen = {}
            for k, v in zip(node.keys, node.values):
                if not isinstance(k, ast.Constant):
                    continue
                val = ast.unparse(v)
                if k.value in seen and seen[k.value] != val:
                    report(path, k.lineno,
                           f"ключ {k.value!r} повторён с ДРУГИМ значением; "
                           f"раннее значение недостижимо")
                seen[k.value] = val


# --------------------------------------------------------------------------
def check_growth(report):
    """Таблицы, в которые пишут, но никогда не удаляют и не чистят каскадом."""
    known_unbounded = {
        # Осознанно живут долго: на них держатся дедупликация, зеркала и теги.
        "FileRegistry", "FileOwners", "FileMirrors",
        # Ограничены по природе: строка на настройку / строка состояния.
        "SystemSettings", "FTSState",
        # Сроки хранения тут продуктовое решение, а не техническое.
        "Feedback", "UserAlerts", "ThreadUnlocks",
    }
    tmp, dbp = _fresh_db()
    con = sqlite3.connect(dbp)
    try:
        tables = [
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%' "
                "AND name NOT LIKE '%_data' AND name NOT LIKE '%_idx' "
                "AND name NOT LIKE '%_content' AND name NOT LIKE '%_docsize' "
                "AND name NOT LIKE '%_config'"
            )
        ]
        cascade = {
            t for t in tables
            if any(r[6] == "CASCADE" for r in con.execute(f"PRAGMA foreign_key_list({t})"))
        }
        blob = ""
        for path in _py_files():
            src, _ = _parse(path)
            if src:
                blob += src
        # Таблицы из списка _cleanup_orphans чистятся общим механизмом:
        # DELETE там собирается динамически по имени таблицы, поэтому поиск
        # текста "DELETE FROM <таблица>" их не находит.
        orphan_swept = set()
        dbsrc, _ = _parse("common/database.py")
        if dbsrc and "cleanup_targets" in dbsrc:
            chunk = dbsrc.split("cleanup_targets", 1)[1].split("]", 1)[0]
            orphan_swept = set(re.findall(r'\(\s*"(\w+)"', chunk))

        for t in sorted(tables):
            if t in known_unbounded or t in cascade or t in orphan_swept:
                continue
            ins = re.search(rf"INSERT (OR \w+ )?INTO {t}\b", blob, re.I)
            dele = re.search(rf"DELETE FROM {t}\b", blob, re.I)
            if ins and not dele:
                report("common/database.py", 0,
                       f"таблица {t}: есть INSERT, нет ни DELETE, ни ON DELETE CASCADE "
                       f"- растёт без границ")
    finally:
        con.close()
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
def check_handlers(report):
    """Команды и callback-и, зарегистрированные дважды.

    В aiogram апдейт забирает ПЕРВЫЙ подошедший обработчик, остальные
    мертвы. Отдельно ловим точное совпадение F.data, съеденное более ранним
    фильтром startswith.
    """
    src, tree = _parse("main.py")
    if tree is None:
        return
    cmds = defaultdict(list)
    order = 0
    filters = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            u = ast.unparse(d)
            if u.startswith("dp.message"):
                order += 1
                for c in ast.walk(d):
                    if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "Command":
                        for a in c.args:
                            vals = (
                                [a.value] if isinstance(a, ast.Constant)
                                else [e.value for e in getattr(a, "elts", [])
                                      if isinstance(e, ast.Constant)]
                            )
                            for v in vals:
                                if isinstance(v, str):
                                    cmds[v.lower()].append((order, node.lineno, node.name))
            elif "dp.callback_query" in u:
                order += 1
                for c in ast.walk(d):
                    if isinstance(c, ast.Compare) and "F.data" in ast.unparse(c.left):
                        for cm in c.comparators:
                            if isinstance(cm, ast.Constant) and isinstance(cm.value, str):
                                filters.append((order, "==", cm.value, node.lineno, node.name))
                    if (isinstance(c, ast.Call) and "startswith" in ast.unparse(c.func)
                            and "F.data" in ast.unparse(c.func)):
                        for a in c.args:
                            for e in ([a] if isinstance(a, ast.Constant)
                                      else getattr(a, "elts", [])):
                                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                                    filters.append(
                                        (order, "startswith", e.value, node.lineno, node.name)
                                    )
    # /admin намеренно ведёт в админ-панель, а не в репорт-флоу.
    for cmd, occ in cmds.items():
        if len(occ) > 1 and cmd != "admin":
            occ.sort()
            dead = ", ".join(f"{fn}():{ln}" for _, ln, fn in occ[1:])
            report("main.py", occ[0][1],
                   f"/{cmd} зарегистрирована {len(occ)} раза; работает {occ[0][2]}(), "
                   f"мертвы: {dead}")
    for o1, t1, v1, l1, f1 in filters:
        for o2, t2, v2, l2, f2 in filters:
            if o2 >= o1:
                continue
            if t2 == "startswith" and v1.startswith(v2) and v1 != v2:
                report("main.py", l1,
                       f"callback '{v1}' -> {f1}() недостижим: раньше зарегистрирован "
                       f"startswith('{v2}') -> {f2}() строка {l2}")
            elif t2 == "==" and t1 == "==" and v1 == v2:
                report("main.py", l1,
                       f"callback '{v1}' -> {f1}() дублирует {f2}() строка {l2}")


def check_decorators(report):
    """Декоратор регистрации, попавший не на ту функцию.

    Реальный случай: хелпер вставили между @dp.message_reaction() и
    обработчиком, декоратор достался хелперу, а настоящий обработчик
    реакций перестал регистрироваться. Ловим по первому параметру: у
    обработчика aiogram он всегда объект события, а не bot/chat_id/text.
    """
    expect = {
        "dp.message": ("message", "msg", "event"),
        "dp.edited_message": ("message", "msg", "event"),
        "dp.callback_query": ("callback", "call", "query", "cb", "event"),
        "dp.message_reaction": ("reaction", "event", "update"),
        "dp.inline_query": ("query", "inline_query", "event"),
        "dp.chat_member": ("update", "event", "chat_member_update"),
        "dp.my_chat_member": ("update", "event", "chat_member_update"),
    }
    for path in LIVE:
        src, tree = _parse(path)
        if tree is None:
            continue
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                u = ast.unparse(d)
                base = u.split("(")[0]
                names = expect.get(base)
                if names is None:
                    continue
                args = node.args.posonlyargs + node.args.args
                if not args:
                    report(path, node.lineno,
                           f"{base} на {node.name}(), у которой нет ни одного параметра")
                    continue
                first = args[0].arg
                if not any(n in first for n in names):
                    report(path, node.lineno,
                           f"{base} навешен на {node.name}(), первый параметр '{first}' "
                           f"не похож на объект события (ожидалось одно из {list(names)}); "
                           f"проверь, не вставлена ли функция между декоратором и обработчиком")


def check_captions(report):
    """Обращение к атрибуту message.text там, где text может быть None.

    У сообщения с картинкой текст лежит в caption, а text равен None -
    message.text.split() падает с AttributeError. Так в этом проекте
    ломались восемь команд, отправленных подписью к медиа: фильтр Command
    в aiogram смотрит и text, и caption, поэтому обработчик вызывался, а
    внутри разбирал только text.

    Считаем обращение защищённым, если где-то в той же функции text
    проверяется на истинность (if message.text / message.text and ... /
    message.text or message.caption). Это приблизительно, зато без шума:
    точный анализ потока тут не нужен, важно поймать функцию, которая о
    None не думает вовсе.
    """
    EVENTISH = {"message", "msg", "m", "event"}
    for path in LIVE:
        src, tree = _parse(path)
        if tree is None:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # где text/caption попадает в булев контекст внутри этой функции
            guarded_bases = set()
            for node in ast.walk(fn):
                tests = []
                if isinstance(node, ast.If):
                    tests.append(node.test)
                elif isinstance(node, ast.BoolOp):
                    tests.extend(node.values)
                elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                    tests.append(node.operand)
                for t in tests:
                    for sub in ast.walk(t):
                        if (isinstance(sub, ast.Attribute) and sub.attr in ("text", "caption")
                                and isinstance(sub.value, ast.Name)):
                            guarded_bases.add(sub.value.id)
            for node in ast.walk(fn):
                if not isinstance(node, ast.Attribute):
                    continue
                inner = node.value
                if not (isinstance(inner, ast.Attribute) and inner.attr == "text"):
                    continue
                base = inner.value
                if not (isinstance(base, ast.Name) and base.id in EVENTISH):
                    continue
                if base.id in guarded_bases:
                    continue
                report(path, node.lineno,
                       f"{fn.name}(): {base.id}.text.{node.attr} без проверки на None - "
                       f"у сообщения с медиа текст лежит в caption, а text равен None")


CHECKS = {
    "dup": ("затенённые определения", check_dup),
    "decor": ("декораторы на чужих функциях", check_decorators),
    "captions": ("message.text без защиты от None", check_captions),
    "arity": ("несовпадение арности вызовов", check_arity),
    "sql": ("SQL против чистой схемы", check_sql),
    "invars": ("IN (...) без разбиения на пачки", check_invars),
    "dictkeys": ("повторяющиеся ключи словаря", check_dictkeys),
    "growth": ("таблицы без очистки", check_growth),
    "handlers": ("дублирующиеся обработчики", check_handlers),
}

# Этим двум нужна временная БД, поднятая настоящим initialize_database, -
# это и есть основная их стоимость. --fast их пропускает.
DB_CHECKS = {"sql", "growth"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checks", nargs="*", help="какие проверки запустить (по умолчанию все)")
    ap.add_argument("--list", action="store_true", help="перечислить проверки и выйти")
    ap.add_argument("--fast", action="store_true",
                    help="только проверки по AST, без поднятия временной БД")
    args = ap.parse_args(argv)

    if args.list:
        for key, (title, fn) in CHECKS.items():
            slow = " (поднимает временную БД)" if key in DB_CHECKS else ""
            print(f"  {key:<10} {title}{slow}")
        return 0

    if args.fast and args.checks:
        print("--fast и явный список проверок вместе не имеют смысла")
        return 2
    selected = args.checks or [k for k in CHECKS if not (args.fast and k in DB_CHECKS)]
    unknown = [c for c in selected if c not in CHECKS]
    if unknown:
        print(f"неизвестные проверки: {unknown}; доступны: {list(CHECKS)}")
        return 2

    total = 0
    for key in selected:
        title, fn = CHECKS[key]
        found = []
        fn(lambda path, line, msg: found.append((path, line, msg)))
        mark = "OK  " if not found else "НАЙД"
        print(f"[{mark}] {key:<10} {title}: {len(found)}")
        for path, line, msg in sorted(found):
            loc = f"{path}:{line}" if line else path
            print(f"         {loc}  {msg}")
        total += len(found)

    print(f"\nвсего замечаний: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
