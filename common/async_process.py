from __future__ import annotations

import asyncio
from collections.abc import Sequence


class AsyncProcessError(RuntimeError):
    def __init__(self, executable: str, returncode: int) -> None:
        super().__init__(f"{executable} exited with code {returncode}")
        self.executable = executable
        self.returncode = returncode


async def run_process_checked(args: Sequence[str], timeout: float | None = None) -> None:
    if not args:
        raise ValueError("empty process command")

    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            process.kill()
        except Exception:
            pass
        try:
            await process.wait()
        except Exception:
            pass
        raise

    if process.returncode != 0:
        raise AsyncProcessError(str(args[0]), int(process.returncode or 0))
