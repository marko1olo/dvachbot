import os
import asyncio
import httpx
from dotenv import load_dotenv

# Загружаем текущий конфиг
load_dotenv()

HF_ACCOUNTS_RAW = os.getenv("HF_ACCOUNTS", "")

async def check_token(token, repo):
    headers = {"Authorization": f"Bearer {token}"}
    
    # ИСПОЛЬЗУЕМ ТОЧНО ТАКУЮ ЖЕ КОНФИГУРАЦИЮ СЕТИ, КАК В MAIN.PY
    # local_address="0.0.0.0" критически важен для работы через VPN в TUN режиме
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=3)
    
    try:
        async with httpx.AsyncClient(
            transport=transport, 
            timeout=20.0, 
            verify=False, 
            trust_env=True # Разрешаем использовать системные настройки (если нужны)
        ) as client:
            
            # 1. Проверка токена (жив ли аккаунт)
            resp = await client.get("https://huggingface.co/api/whoami", headers=headers)
            
            if resp.status_code == 200:
                user_info = resp.json()
                username = user_info.get('name')
                
                # 2. Проверка доступа к репозиторию
                repo_resp = await client.get(f"https://huggingface.co/api/datasets/{repo}", headers=headers)
                
                if repo_resp.status_code == 200:
                    print(f"✅ LIVE: {repo} (User: {username})")
                    return f"{token}:{repo}"
                elif repo_resp.status_code == 404:
                    print(f"⚠️ REPO MISSING: {repo} (User: {username} is alive, but repo deleted)")
                    return None
                elif repo_resp.status_code in [401, 403]:
                     print(f"🔒 REPO LOCKED: {repo} (Access Denied)")
                     return None
                else:
                    print(f"❓ REPO ERR {repo_resp.status_code}: {repo}")
                    return None
            
            elif resp.status_code == 401:
                print(f"❌ BANNED: {repo} (Token invalid/Account locked)")
                return None
            else:
                print(f"⚠️ API ERR {resp.status_code}: {repo}")
                return None
                
    except Exception as e:
        print(f"🔥 NET ERROR: {repo} - {e}")
        return None

async def main():
    if not HF_ACCOUNTS_RAW:
        print("В .env не найден HF_ACCOUNTS")
        return

    accounts = [x.strip() for x in HF_ACCOUNTS_RAW.split(',') if x.strip()]
    print(f"Проверка {len(accounts)} аккаунтов (Bind: 0.0.0.0)...")
    
    tasks = []
    for acc in accounts:
        if ':' not in acc: continue
        token, repo = acc.split(':', 1)
        tasks.append(check_token(token, repo))
        
    results = await asyncio.gather(*tasks)
    valid_accounts = [r for r in results if r]
    
    # Удаляем дубликаты
    valid_accounts = list(set(valid_accounts))
    
    print("\n" + "="*30)
    print("НОВАЯ СТРОКА ДЛЯ .env (Копируй это):")
    print("="*30)
    print(f"HF_ACCOUNTS={','.join(valid_accounts)}")
    print("="*30)

if __name__ == "__main__":
    asyncio.run(main())