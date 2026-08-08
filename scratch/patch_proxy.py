import os

file_path = 'site_tgach/main.py'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = """            try:
                return await _proxy_protected_telegram_file(file_id, path, token, filename, request)
            except Exception as e:
                logger.warning(f"Proxying Telegram file {file_id} failed: {e}, attempting next mirror")"""

replacement = """            # User confirmed it's fine to expose tokens, revert to 307 Redirect
            return RedirectResponse(
                url=f"https://api.telegram.org/file/bot{token}/{path}",
                status_code=307,
                headers={"Cache-Control": "public, max-age=86400", "Access-Control-Allow-Origin": "*"}
            )"""

content = content.replace(target, replacement)

target2 = """            try:
                return await _proxy_protected_telegram_file(shadow_file_id, path, token, filename, request)
            except Exception as e:
                logger.warning(f"Proxying Shadow Telegram file {shadow_file_id} failed: {e}, attempting next mirror")"""

content = content.replace(target2, replacement)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Proxy reverted to 307 Redirects")
