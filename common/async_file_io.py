from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import AsyncIterable, Iterable
from typing import Any, BinaryIO


def copy_fileobj_to_temp(source: BinaryIO, suffix: str = ".tmp") -> str:
    path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as target:
            path = target.name
            shutil.copyfileobj(source, target)
        return path
    except Exception:
        if path:
            remove_files_best_effort((path,))
        raise


async def copy_fileobj_to_temp_async(source: BinaryIO, suffix: str = ".tmp") -> str:
    return await asyncio.to_thread(copy_fileobj_to_temp, source, suffix)


def read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as source:
        return source.read()


async def read_file_bytes_async(path: str) -> bytes:
    return await asyncio.to_thread(read_file_bytes, path)


def read_json_file(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as source:
        return json.load(source)


async def read_json_file_async(path: str) -> Any:
    return await asyncio.to_thread(read_json_file, path)


def open_binary_writer(path: str) -> BinaryIO:
    return open(path, "wb")


async def write_async_iter_bytes_to_file(chunks: AsyncIterable[bytes], path: str) -> None:
    handle = await asyncio.to_thread(open_binary_writer, path)
    try:
        async for chunk in chunks:
            if chunk:
                await asyncio.to_thread(handle.write, chunk)
    finally:
        await asyncio.to_thread(handle.close)


def remove_files_best_effort(paths: Iterable[str]) -> None:
    for path in paths:
        if not path:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


async def remove_files_best_effort_async(paths: Iterable[str]) -> None:
    await asyncio.to_thread(remove_files_best_effort, tuple(paths))
