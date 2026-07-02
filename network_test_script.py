import asyncio
import os

import aiohttp
from dotenv import load_dotenv

from common.secret_redaction import redact_secrets


load_dotenv()

BOT_TOKEN = os.getenv("NETWORK_TEST_BOT_TOKEN") or os.getenv("FILE_UPLOADER_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("NETWORK_TEST_CHANNEL_ID", "-1002940230858"))


def safe_print_response(prefix: str, value: object) -> None:
    print(prefix, redact_secrets(value))


async def run_test() -> None:
    if not BOT_TOKEN:
        print("NETWORK_TEST_BOT_TOKEN or FILE_UPLOADER_BOT_TOKEN is not set.")
        return

    print("Starting Telegram network test...")
    try:
        data = aiohttp.FormData()
        data.add_field("chat_id", str(CHANNEL_ID))
        data.add_field("document", b"this is a test file", filename="test.txt", content_type="text/plain")

        async with aiohttp.ClientSession() as session:
            print("Sending POST request to https://api.telegram.org/bot.../sendDocument")
            async with session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data=data,
                timeout=30,
            ) as response:
                print("Telegram response status:", response.status)
                response_json = await response.json()

                if response.ok:
                    print("SUCCESS: test file sent.")
                    safe_print_response("Server response:", response_json)
                else:
                    print("FAIL: Telegram returned an error.")
                    safe_print_response("Server response:", response_json)

    except asyncio.TimeoutError:
        print("FAIL: connection timed out after 30 seconds.")
    except aiohttp.ClientConnectorError as exc:
        safe_print_response("FAIL: connection error:", exc)
        print("The failure is network/firewall related, not a project logic failure.")
    except Exception as exc:
        safe_print_response("FAIL: unexpected error:", f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(run_test())
