import os

content = """
@app.get("/api/is-ru")
async def check_if_ru(request: Request):
    client_ip = get_real_ip(request)
    user_country = await get_country_by_ip(client_ip)
    is_ru = user_country == "RU"
    if user_country == "XX" or client_ip in ("127.0.0.1", "localhost", "::1"):
        accept_lang = request.headers.get("accept-language", "").lower()
        if "ru" in accept_lang or not accept_lang:
            is_ru = True
    return {"is_ru": is_ru}
"""

with open('site_tgach/main.py', 'a', encoding='utf-8') as f:
    f.write(content)

with open('Dubsite_tgach/main.py', 'a', encoding='utf-8') as f:
    f.write(content.replace('check_if_ru', 'check_if_ru_dub'))
