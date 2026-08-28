import sys

def patch_file():
    path = 'site_tgach/vision.py'
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    start_marker = '            models_cascade = models_pool[start_idx:] + models_pool[:start_idx]'
    end_marker = '            logger.error(f"❌ [VISION] [{source}] Image analysis failed: all vision models exhausted.")\n            return "error_api_exhausted"'
    
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print('Start marker not found')
        return
        
    end_idx = content.find(end_marker)
    if end_idx == -1:
        print('End marker not found')
        return
        
    end_idx += len(end_marker)
    
    new_code = '''            models_cascade = models_pool[start_idx:] + models_pool[:start_idx]
            
            permanent_model_failures = 0

            for model_name, provider in models_cascade:
                if provider == "groq":
                    keys = [k for k in groq_keys if k and k not in BANNED_GROQ_KEYS]
                    base_url = "https://api.groq.com/openai/v1"
                elif provider == "gemini":
                    keys = [k for k in gemini_keys if k and k not in BANNED_GEMINI_KEYS]
                    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
                else:
                    continue

                if keys:
                    available_keys = list(keys)
                    random.shuffle(available_keys)
                    
                    while available_keys:
                        selected_key = None
                        sleep_time = 0.0
                        
                        async with _KEY_RATE_LOCK:
                            now = time.time()
                            # PASS 1: Try to find a completely free key (no sleep)
                            for api_key in available_keys:
                                last_call = _LAST_VISION_CALL_TIME.get(api_key, 0.0)
                                if last_call > now + 10.0:
                                    continue
                                if last_call <= now and (now - last_call) >= 2.5:
                                    selected_key = api_key
                                    sleep_time = 0.0
                                    _LAST_VISION_CALL_TIME[api_key] = now + 2.5
                                    break
                                    
                            # PASS 2: Find key with the minimum wait time
                            if not selected_key:
                                best_key = None
                                min_wait = float('inf')
                                for api_key in available_keys:
                                    last_call = _LAST_VISION_CALL_TIME.get(api_key, 0.0)
                                    if last_call > now + 10.0:
                                        continue
                                    wait_time = last_call - now if last_call > now else 2.5 - (now - last_call)
                                    if wait_time < min_wait:
                                        min_wait = wait_time
                                        best_key = api_key
                                if best_key:
                                    selected_key = best_key
                                    sleep_time = min_wait
                                    _LAST_VISION_CALL_TIME[selected_key] = now + sleep_time + 2.5

                        if not selected_key:
                            logger.warning(f"⚠️ [VISION] [{source}] All keys for {model_name} are penalized. Skipping model.")
                            break
                            
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)

                        try:
                            client = AsyncOpenAI(
                                api_key=selected_key,
                                base_url=base_url,
                                http_client=http_client,
                                max_retries=0,
                                timeout=GROQ_HTTP_TIMEOUT_SECONDS,
                            )
                            prompt_text = system_prompt + "\\nDo NOT generate thinking tags or reasoning. Output only JSON immediately."
                            content_arr = [{"type": "text", "text": prompt_text}]
                            for iu in processed_image_urls:
                                content_arr.append({"type": "image_url", "image_url": {"url": iu}})
                            
                            kwargs = {
                                "model": model_name,
                                "messages": [{"role": "user", "content": content_arr}],
                                "max_tokens": 1500,
                            }
                            if provider == "gemini":
                                kwargs["response_format"] = {"type": "json_object"}
                                
                            if provider == "groq":
                                kwargs["temperature"] = 0.2
                                
                            resp = await client.chat.completions.create(**kwargs)
                            content = resp.choices[0].message.content
                            
                            if content:
                                # Quick cleanup just in case
                                if "<think>" in content:
                                    import re
                                    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                                content = content.replace("```json", "").replace("```", "").strip()
                                
                                try:
                                    # Extract JSON substring if the model added conversational text
                                    start_idx_c = content.find('{')
                                    end_idx_c = content.rfind('}')
                                    if start_idx_c != -1 and end_idx_c != -1 and end_idx_c > start_idx_c:
                                        json_str = content[start_idx_c:end_idx_c+1]
                                    else:
                                        json_str = content
                                        
                                    import json
                                    parsed = json.loads(json_str)
                                    if "tags" in parsed and "description" in parsed:
                                        logger.info(f"👁️ [VISION] [{source}] ✅ Success via {provider} ({model_name}).")
                                        return json.dumps(parsed, ensure_ascii=False)
                                    else:
                                        logger.warning(f"⚠️ [VISION] [{source}] {provider} JSON missing 'tags'/'description' keys. Trying next model.")
                                        permanent_model_failures += 1
                                        break  # malformed schema — next model
                                except json.JSONDecodeError:
                                    # Fallback if model failed JSON format
                                    logger.warning(f"⚠️ [VISION] [{source}] {provider} returned invalid JSON. Using raw content as description.")
                                    return json.dumps({"tags": "parse_error", "description": content}, ensure_ascii=False)

                            else:
                                # Empty response — model returned nothing, try next key
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} ({model_name}) returned empty content. Trying next key.")
                                available_keys.remove(selected_key)
                                continue
                        except Exception as e:
                            err_str = str(e).lower()
                            if "413" in err_str: return "error_413"
                            if "json_validate" in err_str or "max completion tokens" in err_str or "400" in err_str:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} model {model_name} failed ({err_str[:120]}). Trying next model...")
                                permanent_model_failures += 1
                                break
                            if "503" in err_str or "504" in err_str or "unavailable" in err_str or "500" in err_str:
                                logger.warning(f"⚠️ [VISION] [{source}] {provider} server overloaded ({err_str}). Skipping model {model_name}.")
                                break
                            if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                                logger.info(f"ℹ️ [VISION] [{source}] {provider} key {selected_key[:8]}... rate limited (429). Penalizing and trying next key.")
                                async with _KEY_RATE_LOCK:
                                    _LAST_VISION_CALL_TIME[selected_key] = time.time() + 60.0
                                available_keys.remove(selected_key)
                                continue
                            if "401" in err_str or "invalid api key" in err_str or "unauthorized" in err_str:
                                if provider == "groq":
                                    logger.error(f"❌ [VISION] [{source}] Groq key {selected_key[:12]}... unauthorized (401). Removing from pool.")
                                    BANNED_GROQ_KEYS.add(selected_key)
                                available_keys.remove(selected_key)
                                continue
                            if provider == "gemini" and ("403" in err_str or "permission_denied" in err_str):
                                logger.error(f"❌ [VISION] [{source}] Gemini key {selected_key[:12]}... is permanently banned (403). Removing from pool.")
                                BANNED_GEMINI_KEYS.add(selected_key)
                                available_keys.remove(selected_key)
                                continue
                            
                            logger.warning(f"⚠️ [VISION] [{source}] {provider} key failed ({model_name}): {e}")
                            available_keys.remove(selected_key)
                            continue
                            
            if permanent_model_failures >= len(models_cascade):
                logger.error(f"❌ [VISION] [{source}] Image rejected by all models (permanent error). Marking as invalid.")
                return "error_file_invalid"
                
            logger.error(f"❌ [VISION] [{source}] Image analysis failed: all vision models exhausted.")
            return "error_api_exhausted"'''
                            
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content[:start_idx] + new_code + content[end_idx:])
    print('OK')

if __name__ == '__main__':
    patch_file()
