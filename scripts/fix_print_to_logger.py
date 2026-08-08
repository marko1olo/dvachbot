"""
Replaces standalone print() calls in main.py with appropriate logger.* calls.
Rules:
  - Lines containing ⛔, ошибк, Error, except  → logger.error
  - Lines containing ⚠️, Warning, Конфликт     → logger.warning
  - All others                                  → logger.info
Does NOT touch print() calls that are inside f-string expressions or multiline constructs.
"""
import re, sys, shutil, pathlib

TARGET = pathlib.Path(r"C:\Users\danat\Desktop\dvachbot\main.py")
BACKUP = TARGET.with_suffix(".py.bak_print")

# Backup
shutil.copy2(TARGET, BACKUP)
print(f"Backup saved: {BACKUP}", file=sys.stderr)

lines = TARGET.read_text(encoding="utf-8").splitlines(keepends=True)

# Pattern: leading whitespace + print( ... )   — single-line only
PRINT_RE = re.compile(r'^(\s*)print\((.+)\)\s*$')

# Keywords that indicate error/warning level
ERROR_KEYWORDS = ('⛔', 'ошибк', 'Error', 'error', 'except', 'Failed', 'fail', 'ОШИБКА', 'traceback', 'Traceback')
WARN_KEYWORDS  = ('⚠️', 'Warn', 'warn', 'Конфликт', 'не улож', 'не найд', 'не сохран')

changed = 0
result_lines = []
for i, line in enumerate(lines, 1):
    m = PRINT_RE.match(line)
    if m:
        indent, body = m.group(1), m.group(2)
        # Determine level
        if any(k in body for k in ERROR_KEYWORDS):
            level = "error"
        elif any(k in body for k in WARN_KEYWORDS):
            level = "warning"
        else:
            level = "info"
        new_line = f"{indent}logger.{level}({body})\n"
        result_lines.append(new_line)
        changed += 1
    else:
        result_lines.append(line)

TARGET.write_text("".join(result_lines), encoding="utf-8")
print(f"Done. Replaced {changed} print() calls in {TARGET.name}", file=sys.stderr)
