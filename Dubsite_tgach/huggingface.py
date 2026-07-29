import os
import logging
from io import BytesIO
from huggingface_hub import HfApi
from common.env_utils import proxy_env
from common.token_pool import hf_accounts

logger = logging.getLogger("huggingface")

PROXY_URL = os.getenv("HTTPS_PROXY") or "http://127.0.0.1:10808"

def _upload_sync(file_bytes: bytes, filename: str) -> str | None:
    token, repo_id = hf_accounts.get_pair()
    if not token or not repo_id:
        return None

    if len(filename) >= 2:
        subfolder = filename[:2]
    else:
        subfolder = "misc"
    path_in_repo = f"media/{subfolder}/{filename}"

    strategies = [
        {"name": "Proxy", "proxy": PROXY_URL},
        {"name": "Direct/System", "proxy": None},
    ]

    for strategy in strategies:
        try:
            # Прокси ставится только на время попытки и снимается после.
            # Раньше os.environ.pop выполнялся без восстановления и снимал
            # прокси со всего процесса, включая сессии с trust_env=True.
            with proxy_env(strategy["proxy"]):
                api = HfApi(token=token)

                api.upload_file(
                    path_or_fileobj=BytesIO(file_bytes),
                    path_in_repo=path_in_repo,
                    repo_id=repo_id,
                    repo_type="dataset"
                )
            return f"https://huggingface.co/datasets/{repo_id}/resolve/main/{path_in_repo}"
        
        except Exception as e:
            logger.warning(f"HF Upload ({strategy['name']}) failed: {e}")
            continue
            
    return None

async def upload_to_hf(file_bytes: bytes, filename: str) -> str | None:
    # HuggingFace is disabled/dead
    return None