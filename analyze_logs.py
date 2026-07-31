import re
from collections import defaultdict
from datetime import datetime, timedelta


def analyze_visitors_log(filepath):
    # Regex patterns
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \| \[(.*?)\] (.*?)(?: \| (.*))?$"
    )
    enter_pattern = re.compile(r"^([\d\.]+) \((.*?)\)$")

    cutoff_date = datetime.now() - timedelta(days=2)

    total_requests = 0
    unique_ips = set()
    countries = defaultdict(int)
    ip_stats = defaultdict(
        lambda: {
            "requests": 0,
            "is_live": False,
            "country": "Unknown",
            "endpoints": defaultdict(int),
        }
    )

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            match = log_pattern.match(line.strip())
            if not match:
                continue

            date_str, action_type, ip_part, action_detail = match.groups()

            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                if dt < cutoff_date:
                    continue
            except ValueError:
                continue

            if action_type == "ENTER":
                enter_match = enter_pattern.match(ip_part)
                if enter_match:
                    ip = enter_match.group(1)
                    country = enter_match.group(2)
                    ip_stats[ip]["country"] = country
                    countries[country] += 1
            elif action_type == "LIVE":
                ip = ip_part.strip()
                ip_stats[ip]["is_live"] = True
            elif action_type == "DO":
                ip = ip_part.strip()
                ip_stats[ip]["requests"] += 1
                total_requests += 1
                unique_ips.add(ip)
                if action_detail:
                    if action_detail.startswith("GET ") or action_detail.startswith(
                        "POST "
                    ):
                        endpoint = action_detail.split()[1].split("?")[0]
                        ip_stats[ip]["endpoints"][endpoint] += 1

    # Analysis
    real_users = 0
    bots = 0

    top_endpoints = defaultdict(int)

    for ip, data in ip_stats.items():
        if data["requests"] == 0:
            continue

        # If they triggered LIVE (WebSocket), they are highly likely human
        if data["is_live"]:
            real_users += 1
        # If they didn't trigger LIVE, made very few requests, or only hit APIs/files, they might be bots/crawlers
        else:
            bots += 1

        for ep, count in data["endpoints"].items():
            top_endpoints[ep] += count

    # Sort countries
    sorted_countries = sorted(countries.items(), key=lambda x: x[1], reverse=True)[:10]
    sorted_endpoints = sorted(top_endpoints.items(), key=lambda x: x[1], reverse=True)[
        :10
    ]

    # Format markdown
    md = f"""# Аналитика сайта (последние 48 часов)

## Общая сводка
- **Уникальных IP:** {len(unique_ips)}
- **Всего запросов/действий:** {total_requests}
- **Предположительно Живых людей:** {real_users} (Активировали WebSocket/JS сессию)
- **Предположительно Ботов/Скриптов/Парсеров:** {bots} (Запрашивали страницы, но не открыли WS)

## География (Топ 10 стран)
"""
    for c, count in sorted_countries:
        md += f"- **{c}**: {count} уников\n"

    md += "\n## Популярные запросы (Топ 10)\n"
    for ep, count in sorted_endpoints:
        md += f"- `{ep}`: {count} раз\n"

    md += "\n## Активность ботов\n"
    md += "Многие 'боты' могут быть также пользователями с отключенным JS или парсерами превью (Telegram/Discord/VK). "
    md += "Они генерируют запросы к `/files/...` или `/api/thread/...` напрямую."

    with open("site_stats.md", "w", encoding="utf-8") as out:
        out.write(md)


if __name__ == "__main__":
    analyze_visitors_log("visitors.log")
