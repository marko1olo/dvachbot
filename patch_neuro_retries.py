import os
import re

def patch_neuro_poster(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'api_retry' in content: return
    
    # 1. Add imports
    content = content.replace('import asyncio', 'import asyncio\nfrom common.http_utils import api_retry')
    
    # 2. Add wrapper
    wrapper = """
@api_retry
async def _execute_completion(client, model, messages, max_tokens, temperature):
    return await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    )
"""
    content = content.replace('def get_groq_logger():', wrapper + '\ndef get_groq_logger():')
    
    # 3. Replace call
    old_call = """completion = await client.chat.completions.create(
                                model=target_model,
                                messages=messages,
                                max_tokens=max_tokens,
                                temperature=temperature
                            )"""
    new_call = """completion = await _execute_completion(client, target_model, messages, max_tokens, temperature)"""
    content = content.replace(old_call, new_call)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def patch_tagging_worker(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'api_retry' in content: return
    
    content = content.replace('import asyncio', 'import asyncio\nfrom common.http_utils import api_retry')
    
    wrapper = """
@api_retry
async def _execute_tagging(client, model, messages, max_tokens):
    return await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens
    )
"""
    if 'def extract_image_tags' in content:
        content = content.replace('def extract_image_tags', wrapper + '\ndef extract_image_tags')
    elif 'async def run_deep_check' in content:
        content = content.replace('async def run_deep_check', wrapper + '\nasync def run_deep_check')

    old_call = """resp = await client.chat.completions.create(
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": [{"type": "text", "text": TAGGING_PROMPT}, {"type": "image_url", "image_url": {"url": url}}]}],
                        max_tokens=250
                    )"""
    new_call = """resp = await _execute_tagging(
                        client,
                        model=GROQ_MODEL,
                        messages=[{"role": "user", "content": [{"type": "text", "text": TAGGING_PROMPT}, {"type": "image_url", "image_url": {"url": url}}]}],
                        max_tokens=250
                    )"""
    content = content.replace(old_call, new_call)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def patch_neuro_moderator(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'api_retry' in content: return

    content = content.replace('import asyncio', 'import asyncio\nfrom common.http_utils import api_retry')
    
    wrapper = """
@api_retry
async def _execute_groq_post(client, url, headers, json_data):
    return await client.post(url, headers=headers, json=json_data)
"""
    if 'async def neuro_deep_check' in content:
        content = content.replace('async def neuro_deep_check', wrapper + '\nasync def neuro_deep_check')
        
    old_call = """resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "model": GROQ_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": 0.1 # Минимальная температура для строгого JSON
                    }
                )"""
    new_call = """resp = await _execute_groq_post(
                    client,
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {token}"},
                    json_data={
                        "model": GROQ_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": 0.1 # Минимальная температура для строгого JSON
                    }
                )"""
    content = content.replace(old_call, new_call)
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == '__main__':
    for r, d, fs in os.walk('.'):
        for f in fs:
            if 'neuro_poster.py' in f:
                patch_neuro_poster(os.path.join(r, f))
            elif 'tagging_worker.py' in f:
                patch_tagging_worker(os.path.join(r, f))
            elif 'neuro_moderator.py' in f:
                patch_neuro_moderator(os.path.join(r, f))
    print("Neuro files patched with exponential backoff.")
