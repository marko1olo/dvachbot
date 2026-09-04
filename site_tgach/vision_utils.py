import base64
import random
import os
import io
import asyncio
from PIL import Image
import httpx
from openai import AsyncOpenAI
import logging

logger = logging.getLogger(__name__)

async def describe_image_for_bot(img_bytes: bytes, caption: str = "") -> str:
    try:
        # Resize image
        img = Image.open(io.BytesIO(img_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        MAX_SIZE = 800
        if max(img.size) > MAX_SIZE:
            img.thumbnail((MAX_SIZE, MAX_SIZE), Image.Resampling.LANCZOS)
            
        with io.BytesIO() as buffer:
            img.save(buffer, format="JPEG", quality=70, optimize=True)
            resized_bytes = buffer.getvalue()
            
        b64_img = base64.b64encode(resized_bytes).decode("utf-8")
        image_url = f"data:image/jpeg;base64,{b64_img}"
        
        system_prompt = "You are an anonymous toxic user on an imageboard. Describe what you see in the attached image in Russian. Be extremely rude, sarcastic and toxic. Use mat (profanity). Mention any text on the image. Make it 2-3 sentences. Context from author: " + str(caption)
        
        keys_str = os.getenv("GROQ_API_KEYS", "")
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if not keys:
            return "[????????, ?? API ????? ?? ?????????]"
            
        api_key = random.choice(keys)
        
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
        
        resp = await client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            max_tokens=250,
            timeout=15.0
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error describing image: {e}", exc_info=True)
        return f"[?? ??????? ?????????? ?????: {e}]"

