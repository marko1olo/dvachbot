from __future__ import annotations

import asyncio

from common.config import DB_NAME
from common.database import initialize_database


async def main() -> int:
    await initialize_database()
    print("database initialized:", DB_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
