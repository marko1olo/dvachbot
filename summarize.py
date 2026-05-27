# summarize.py
# выполняет суммаризацию текста с помощью Hugging Face API
import aiohttp
import json

async def summarize_text_with_hf(prompt: str, text: str, hf_token: str) -> str:
    # Используем стабильную и проверенную модель для саммаризации русского текста
    url = "https://api-inference.huggingface.co/models/IlyaGusev/rut5_base_sum_gazeta"
    headers = {"Authorization": f"Bearer {hf_token}"}

    # Новая, безопасная логика расчета длины
    text_word_count = len(text.split())
    
    # 1. Сначала вычисляем максимальную длину. Она не должна быть слишком маленькой.
    max_len = max(50, min(600, text_word_count // 3))
    
    # 2. Затем вычисляем минимальную длину на основе максимальной.
    # Это гарантирует, что min_len никогда не будет больше max_len.
    min_len = max(20, max_len // 2)

    payload = {
        "inputs": f"summarize: {prompt}\n\n{text}",
        "parameters": {
            "min_length": min_len,
            "max_length": max_len,
            "no_repeat_ngram_size": 3,
            "early_stopping": True,
        },
        "options": {
            "wait_for_model": True
        }
    }
    print(f"[summarize] payload params: min={min_len}, max={max_len}, textlen={len(text)}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=180) as resp:
                response_text = await resp.text()
                
                if resp.status != 200:
                    print(f"[summarize] HF API error. Status: {resp.status}, Response: {response_text}")
                    return ""
                    
                try:
                    data = json.loads(response_text)
                    if isinstance(data, list) and data and 'summary_text' in data[0]:
                        print("[summarize] HF API summary success")
                        return data[0]['summary_text']
                    
                    print(f"[summarize] HF API response format error: {data}")
                    return ""
                except json.JSONDecodeError:
                    print(f"[summarize] HF API JSON decode error. Response: {response_text}")
                    return ""

    except Exception as e:
        import traceback
        print(f"[summarize] Exception in summarize_text_with_hf: {e}")
        traceback.print_exc()
        return ""
# --- КОНЕЦ ИЗМЕНЕНИЙ ---