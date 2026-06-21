import httpx
import openai
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type, retry_if_exception

def is_retryable_error(exception):
    """
    Checks if an HTTPStatusError is retryable (429, 500, 502, 503, 504).
    """
    if isinstance(exception, httpx.HTTPStatusError):
        status = exception.response.status_code
        return status in (429, 500, 502, 503, 504)
    return False

# Декоратор для экспоненциального бэкоффа (от 1 до 10 секунд, максимум 5 попыток)
api_retry = retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(5),
    retry=(
        retry_if_exception_type((
            httpx.TimeoutException, 
            httpx.ConnectError,
            httpx.ReadError,
            httpx.WriteError,
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.InternalServerError,
            openai.APITimeoutError
        )) | 
        retry_if_exception(is_retryable_error)
    )
)
