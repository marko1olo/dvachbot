import asyncio
import aiosqlite
import os
from datetime import datetime
import time
import re
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    print("Ошибка: библиотека 'rich' не установлена. Выполните: pip install rich")
    sys.exit(1)

try:
    import psutil
except ImportError:
    psutil = None

DB_NAME = "dvach_bot.db"
LOG_FILE = "site.log"

console = Console()

def format_age(ts):
    if not ts or ts == 0:
        return "[dim]N/A[/dim]"
    
    age_seconds = time.time() - ts
    
    if age_seconds < 60:
        return f"[green]{int(age_seconds)}s ago[/green]"
    if age_seconds < 3600:
        return f"[green]{int(age_seconds / 60)}m ago[/green]"
    if age_seconds < 86400:
        return f"[yellow]{int(age_seconds / 3600)}h ago[/yellow]"
    
    return f"[bold red]{int(age_seconds / 86400)}d ago[/bold red]"

def format_queue_value(value):
    if isinstance(value, str): return f"[bold red]{value}[/bold red]"
    if value > 1000: return f"[bold red]{value:,}[/bold red]"
    if value > 100: return f"[bold yellow]{value:,}[/bold yellow]"
    return f"[green]{value:,}[/green]"

def format_sys_value(value, unit="%"):
    if not isinstance(value, (int, float)): return "[dim]N/A[/dim]"
    if value > 90: return f"[bold red]{value:.1f}{unit}[/bold red]"
    if value > 75: return f"[bold yellow]{value:.1f}{unit}[/bold yellow]"
    return f"[green]{value:.1f}{unit}[/green]"

async def get_queue_details(conn):
    details = {}
    queue_map = {
        "Tagging (Neuro)": ("FileRegistry", "created_at", "(tags IS NULL OR tags = '') AND file_type IN ('image', 'photo')"),
        "HuggingFace": ("PendingHF", "created_at"),
        "Mirrors (Catbox)": ("MirrorQueue", "next_run_at"),
        "Reports": ("Reports", "created_at", "status = 'open'"),
        "Mod Queue (Neuro)": ("ModQueue", "created_at", "status = 'pending'"),
        "Notifications": ("NotificationQueue", "created_at"),
        "Broadcast (WS)": ("BroadcastQueue", "created_at"),
        "Imports": ("ImportRequests", "created_at", "status = 'pending'"),
    }
    for name, info in queue_map.items():
        try:
            query = f"SELECT COUNT(*), MIN({info[1]}) FROM {info[0]} {f'WHERE {info[2]}' if len(info) > 2 else ''}"
            cursor = await conn.execute(query)
            count, oldest_ts = await cursor.fetchone()
            details[name] = {"count": count or 0, "oldest": oldest_ts or 0}
        except aiosqlite.OperationalError:
            details[name] = {"count": "N/A", "oldest": 0}
    return details

async def get_activity(conn):
    now = time.time()
    periods = {"1h": now - 3600, "24h": now - 86400}
    activity = {}
    for name, ts in periods.items():
        try:
            p_cursor, t_cursor, u_cursor = await asyncio.gather(
                conn.execute("SELECT COUNT(*) FROM Posts WHERE timestamp > ?", (ts,)),
                conn.execute("SELECT COUNT(*) FROM Threads WHERE created_at > ?", (ts,)),
                conn.execute("SELECT COUNT(DISTINCT user_id) FROM Users WHERE created_at > ?", (ts,))
            )
            activity[f'posts_{name}'] = (await p_cursor.fetchone())[0]
            activity[f'threads_{name}'] = (await t_cursor.fetchone())[0]
            activity[f'users_{name}'] = (await u_cursor.fetchone())[0]
        except aiosqlite.OperationalError:
            activity[f'posts_{name}'] = activity[f'threads_{name}'] = activity[f'users_{name}'] = "N/A"
    return activity

async def get_media_stats(conn):
    """Собирает детальную статистику по FileRegistry."""
    stats = {}
    queries = {
        "total_files": "SELECT COUNT(sha256) FROM FileRegistry",
        "with_tags": "SELECT COUNT(sha256) FROM FileRegistry WHERE tags IS NOT NULL AND tags != ''",
        "has_phash": "SELECT COUNT(sha256) FROM FileRegistry WHERE phash IS NOT NULL",
        "has_blurhash": "SELECT COUNT(sha256) FROM FileRegistry WHERE blurhash IS NOT NULL",
        "total_thumbnails": "SELECT COUNT(DISTINCT thumbnail_id) FROM FileRegistry WHERE thumbnail_id IS NOT NULL",
    }
    
    results = await asyncio.gather(*[conn.execute(q) for q in queries.values()])
    fetched = await asyncio.gather(*[r.fetchone() for r in results])

    for i, key in enumerate(queries.keys()):
        stats[key] = fetched[i][0] if fetched[i] else 0

    stats['by_type'] = {}
    try:
        type_cursor = await conn.execute("SELECT file_type, COUNT(*) FROM FileRegistry GROUP BY file_type")
        async for row in type_cursor:
            stats['by_type'][row[0] or 'unknown'] = row[1]
    except aiosqlite.OperationalError:
        pass
            
    return stats

async def get_top_activity(conn):
    day_ago = time.time() - 86400
    top = {}
    try:
        boards_cursor = await conn.execute("SELECT board_id, COUNT(*) as c FROM Posts WHERE timestamp > ? GROUP BY board_id ORDER BY c DESC LIMIT 5", (day_ago,))
        threads_cursor = await conn.execute("SELECT thread_id, board_id, title, reply_count FROM Threads WHERE is_archived = 0 ORDER BY last_updated_at DESC LIMIT 5")
        top["boards"] = await boards_cursor.fetchall()
        top["threads"] = await threads_cursor.fetchall()
    except:
        top["boards"], top["threads"] = [], []
    return top
def get_db_file_sizes():
    """Возвращает размеры файлов БД."""
    sizes = {}
    for f in [DB_NAME, f"{DB_NAME}-wal", f"{DB_NAME}-shm"]:
        if os.path.exists(f):
            try:
                size_bytes = os.path.getsize(f)
                sizes[f] = f"{size_bytes / 1024 / 1024:.2f} MB"
            except OSError:
                sizes[f] = "[red]Access Error[/red]"
        else:
            sizes[f] = "[dim]Not found[/dim]"
    return sizes
def get_system_health():
    if not psutil: return {"cpu": "N/A", "ram": "N/A", "disk": "N/A"}
    try:
        return {"cpu": psutil.cpu_percent(interval=0.1), "ram": psutil.virtual_memory().percent, "disk": psutil.disk_usage('/').percent}
    except Exception:
        return {"cpu": "Error", "ram": "Error", "disk": "Error"}

def get_last_errors():
    if not os.path.exists(LOG_FILE): return ["Log file not found."]
    errors = []
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        for line in reversed(lines):
            if "ERROR" in line or "CRITICAL" in line or "Exception" in line:
                errors.append(line.strip().split('] - ', 1)[-1][:200])
            if len(errors) >= 5: break
    except Exception as e:
        errors.append(f"Could not read log file: {e}")
    return errors if errors else ["No errors found in recent logs."]

async def main():
    if not os.path.exists(DB_NAME):
        console.print(f"[bold red]Ошибка: Файл базы данных '{DB_NAME}' не найден![/bold red]")
        return

    console.rule(f"[bold cyan]Отчет о состоянии системы TGACH ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})[/bold cyan]")
    
    async with aiosqlite.connect(DB_NAME) as conn:
        data = await asyncio.gather(
            get_queue_details(conn),
            get_activity(conn),
            get_media_stats(conn),
            get_top_activity(conn),
            asyncio.to_thread(get_system_health),
            asyncio.to_thread(get_last_errors),
            asyncio.to_thread(get_db_file_sizes)
        )
        queues, activity, media_stats, top, sys_health, errors, db_sizes = data

        # --- ОЧЕРЕДИ ---
        q_table = Table(title="🗂️ Системные очереди")
        q_table.add_column("Очередь", style="cyan", overflow="fold")
        q_table.add_column("Размер", justify="right")
        q_table.add_column("Самый старый", justify="right", style="yellow")
        for name, d in queues.items(): q_table.add_row(name, format_queue_value(d['count']), format_age(d['oldest']))
        
        # --- АКТИВНОСТЬ ---
        a_table = Table(title="📈 Активность")
        a_table.add_column("Период", style="cyan")
        a_table.add_column("Посты", justify="right", style="magenta")
        a_table.add_column("Треды", justify="right", style="magenta")
        a_table.add_column("Юзеры", justify="right", style="magenta")
        a_table.add_row("За час", f"{activity.get('posts_1h', 0):,}", f"{activity.get('threads_1h', 0):,}", f"{activity.get('users_1h', 0):,}")
        a_table.add_row("За 24 часа", f"{activity.get('posts_24h', 0):,}", f"{activity.get('threads_24h', 0):,}", f"{activity.get('users_24h', 0):,}")

        # --- МЕДИА ---
        m_table = Table(title="🗃️ Медиа-аналитика (FileRegistry)")
        m_table.add_column("Параметр", style="cyan")
        m_table.add_column("Количество", justify="right")
        m_table.add_column("Соотношение", justify="right", style="magenta")

        total = media_stats.get('total_files', 0)
        if total > 0:
            m_table.add_row("[bold]Всего файлов[/bold]", f"{total:,}", "100%")
            
            tagged = media_stats.get('with_tags', 0)
            phash = media_stats.get('has_phash', 0)
            blur = media_stats.get('has_blurhash', 0)
            
            m_table.add_row("  - с тегами (Tags)", f"{tagged:,}", f"{tagged / total * 100:.1f}%")
            m_table.add_row("  - с перцептивным хешем (pHash)", f"{phash:,}", f"{phash / total * 100:.1f}%")
            m_table.add_row("  - с заглушкой (BlurHash)", f"{blur:,}", f"{blur / total * 100:.1f}%")
            m_table.add_section()
            m_table.add_row("[bold]Разбивка по типам[/bold]", "", "")
            
            sorted_types = sorted(media_stats.get('by_type', {}).items(), key=lambda i: i[1], reverse=True)
            for f_type, count in sorted_types:
                m_table.add_row(f"  - {f_type.capitalize()}", f"{count:,}", f"{count / total * 100:.1f}%")
            m_table.add_section()
            m_table.add_row("[bold]Всего превью[/bold]", f"{media_stats.get('total_thumbnails', 0):,}", "")
        else:
            m_table.add_row("Файлы не найдены", "0", "0%")

        # --- ТОП АКТИВНОСТИ ---
        top_table = Table(title="🏆 Топ Активности (24 часа)")
        top_table.add_column("Топ-5 Досок (по постам)", style="cyan")
        top_table.add_column("Топ-5 Тредов (по бампам)", style="cyan")
        b_text = "\n".join([f"{i+1}. [bold]/{b[0]}[/bold] ({b[1]:,} постов)" for i, b in enumerate(top.get('boards', []))])
        t_text = "\n".join([f"{i+1}. [bold]/{t[1]}/ → #{t[0]}[/bold] ({t[3]} replies)\n   '{t[2][:40]}...'\n" for i, t in enumerate(top.get('threads', []))])
        top_table.add_row(Text.from_markup(b_text), Text.from_markup(t_text))

        # --- Вывод ---
        console.print(q_table)
        console.print(a_table)
        console.print(m_table)
        console.print(top_table)
        
        # --- Системные панели ---
        cpu, ram, disk = format_sys_value(sys_health.get('cpu', 0)), format_sys_value(sys_health.get('ram', 0)), format_sys_value(sys_health.get('disk', 0))
        db_size = db_sizes.get(DB_NAME, "N/A")
        sys_panel = Panel(Text.from_markup(f" [bold]CPU:[/bold] {cpu} | [bold]RAM:[/bold] {ram} | [bold]Disk:[/bold] {disk} | [bold]DB Size:[/bold] {db_size}"), title="💻 Система", border_style="green")
        
        err_panel = Panel(Text.from_markup("\n".join([f"• [dim]{e}[/dim]" for e in errors])), title="🚨 Последние ошибки", border_style="red")
        
        console.print(sys_panel)
        console.print(err_panel)

if __name__ == "__main__":
    if "win" in sys.platform:
        # Эта политика нужна для Windows, чтобы избежать некоторых ошибок asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())