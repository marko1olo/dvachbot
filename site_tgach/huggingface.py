import os
import asyncio
import logging
import hashlib
from io import BytesIO
from huggingface_hub import HfApi
from common.token_pool import hf_accounts
from site_tgach.mirror_health import clear_hf_failure, is_hf_repo_available, mark_hf_upload_failure

logger = logging.getLogger("huggingface")

PROXY_URL = os.getenv("HTTPS_PROXY") or "http://127.0.0.1:10808"

def _upload_sync(file_bytes: bytes, filename: str) -> str | None:
    token, repo_id = hf_accounts.get_pair()
    if not token or not repo_id:
        return None
    if not is_hf_repo_available(repo_id):
        return None

    # Хэшируем имя файла для равномерного распределения по 256 папкам (лимит Git: 10к файлов в папке)
    subfolder = hashlib.md5(filename.encode()).hexdigest()[:2]
    path_in_repo = f"media/{subfolder}/{filename}"

    strategies = [
        {"name": "Proxy", "env": {"HTTPS_PROXY": PROXY_URL, "HTTP_PROXY": PROXY_URL}},
        {"name": "Direct/System", "env": {}}
    ]

    for strategy in strategies:
        try:
            # Очищаем или ставим прокси для текущей попытки
            os.environ.pop("HTTPS_PROXY", None)
            os.environ.pop("HTTP_PROXY", None)
            os.environ.update(strategy["env"])

            api = HfApi(token=token)
            
            api.upload_file(
                path_or_fileobj=BytesIO(file_bytes),
                path_in_repo=path_in_repo,
                repo_id=repo_id,
                repo_type="dataset"
            )
            clear_hf_failure(repo_id)
            return f"https://huggingface.co/datasets/{repo_id}/resolve/main/{path_in_repo}"
        
        except Exception as e:
            if mark_hf_upload_failure(e, repo_id):
                break
            logger.warning(f"HF Upload ({strategy['name']}) failed: {e}")
            continue
            
    return None

async def upload_to_hf(file_bytes: bytes, filename: str) -> str | None:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _upload_sync, file_bytes, filename)
