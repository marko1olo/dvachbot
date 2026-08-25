# -*- coding: utf-8 -*-
"""
stats_hub_router.py — Interactive Next-Gen Telegram Stats Hub Router for DvachBot.
100% standalone, comprehensive alias support and full inline navigation matrix.
"""

import os
import io
import asyncio
import logging
from typing import Optional

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile,
    WebAppInfo
)

import stats_v2
import my_wrapped_generator

logger = logging.getLogger("stats_hub")
router = Router(name="stats_hub_router")

WEBAPP_STATS_URL = os.environ.get("WEBAPP_STATS_URL", "https://tgach.top/app/stats")

def build_stats_hub_keyboard() -> InlineKeyboardMarkup:
    """Builds the main dashboard keyboard with WebApp button and 4 category posters."""
    kb = [
        [
            InlineKeyboardButton(text="💰 Экономика & Казино", callback_data="shub:economy"),
            InlineKeyboardButton(text="⚔️ Войны & PvP", callback_data="shub:pvp")
        ],
        [
            InlineKeyboardButton(text="🧠 Социология & Бифы", callback_data="shub:drama"),
            InlineKeyboardButton(text="🖼️ Мемы & Баянометр", callback_data="shub:memes")
        ],
        [
            InlineKeyboardButton(text="🎴 Мой 2ch Wrapped", callback_data="shub:wrapped"),
            InlineKeyboardButton(text="🔄 Обновить Пульс", callback_data="shub:refresh")
        ]
    ]
    if WEBAPP_STATS_URL:
        kb.insert(0, [
            InlineKeyboardButton(
                text="📊 Открыть WebApp Дашборд",
                web_app=WebAppInfo(url=WEBAPP_STATS_URL)
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def build_poster_nav_keyboard(current_category: str) -> InlineKeyboardMarkup:
    """Builds navigation keyboard under rendered HD posters."""
    buttons_row1 = []
    if current_category != "economy":
        buttons_row1.append(InlineKeyboardButton(text="💰 Экономика", callback_data="shub:economy"))
    if current_category != "pvp":
        buttons_row1.append(InlineKeyboardButton(text="⚔️ Войны", callback_data="shub:pvp"))
    if current_category != "drama":
        buttons_row1.append(InlineKeyboardButton(text="🧠 Бифы", callback_data="shub:drama"))
    if current_category != "memes":
        buttons_row1.append(InlineKeyboardButton(text="🖼️ Мемы", callback_data="shub:memes"))

    kb = []
    if buttons_row1:
        kb.append(buttons_row1[:2])
        if len(buttons_row1) > 2:
            kb.append(buttons_row1[2:])

    kb.append([
        InlineKeyboardButton(text="🎴 Мой Wrapped", callback_data="shub:wrapped"),
        InlineKeyboardButton(text="🏠 Главный Пульс", callback_data="shub:home")
    ])
    kb = [row for row in kb if row]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- 1. Hub / Pulse / Radar Commands ---
@router.message(Command(
    "stats_hub", "statshub", "stats2", "deck", "shub", "pulse", "radar", "analytics",
    "пульс", "стата2", "борда", "дашборд",
    ignore_case=True, ignore_mention=True
))
async def cmd_stats_hub(message: types.Message, board_id: str | None = None, **kwargs):
    """Entrypoint for standalone stats hub with instant snapshot."""
    try:
        text, _ = await asyncio.to_thread(stats_v2.generate_instant_snapshot_text, board_id=board_id)
        await message.reply(
            text=text,
            parse_mode="HTML",
            reply_markup=build_stats_hub_keyboard(),
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.exception("Error in cmd_stats_hub: %s", e)
        await message.reply(f"⚠️ Ошибка генерации пульса статистики: {e}")


# --- 2. Personal Wrapped Commands ---
@router.message(Command(
    "my_wrapped", "wrapped", "mywrapped", "myposter", "враппед", "мой_срез", "мой_паспорт",
    ignore_case=True, ignore_mention=True
))
async def cmd_my_wrapped(message: types.Message, **kwargs):
    """Generates personalized 2ch Wrapped poster for the user."""
    user_id = message.from_user.id if message.from_user else 0
    status_msg = await message.reply("⏳ <i>Генерирую твой персональный 2ch Wrapped...</i>", parse_mode="HTML")
    try:
        buf = await asyncio.to_thread(my_wrapped_generator.generate_my_wrapped_poster, user_id)
        input_file = BufferedInputFile(buf.getvalue(), filename=f"wrapped_{user_id}.png")
        await message.reply_photo(
            photo=input_file,
            caption="🎴 <b>Твой персональный ТГАЧ Wrapped готов!</b>\nПересылай в тред или хвастайся перед анонами.",
            parse_mode="HTML",
            reply_markup=build_poster_nav_keyboard("wrapped")
        )
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        logger.exception("Error in cmd_my_wrapped: %s", e)
        await status_msg.edit_text(f"⚠️ Ошибка генерации Wrapped: {e}")


# --- 3. Direct Economy / Casino Commands ---
@router.message(Command("economy_stats", "econ", "heists", "casino_stats", "эконом_стата", "стата_казны", "грабежи", "казино_стата", ignore_case=True, ignore_mention=True))
async def cmd_economy_direct(message: types.Message, **kwargs):
    """Direct command for economy HD poster."""
    status_msg = await message.reply("⏳ <i>Рендерю срез экономики...</i>", parse_mode="HTML")
    try:
        buf = await asyncio.to_thread(stats_v2.generate_economy_heists_poster)
        input_file = BufferedInputFile(buf.getvalue(), filename="stats_economy.png")
        await message.reply_photo(
            photo=input_file,
            caption="💰 <b>ТГАЧ Экономика, Казино и Криминал</b>",
            parse_mode="HTML",
            reply_markup=build_poster_nav_keyboard("economy")
        )
        try: await status_msg.delete()
        except Exception: pass
    except Exception as e:
        logger.exception("Error in cmd_economy_direct: %s", e)
        await status_msg.edit_text(f"⚠️ Ошибка: {e}")


# --- 4. Direct PvP / Warfare Commands ---
@router.message(Command("pvp_stats", "war_stats", "combat_stats", "война", "войны", "пвп_стата", "дебаффы", "фольга", ignore_case=True, ignore_mention=True))
async def cmd_pvp_direct(message: types.Message, **kwargs):
    """Direct command for PvP HD poster."""
    status_msg = await message.reply("⏳ <i>Рендерю срез PvP и боевых действий...</i>", parse_mode="HTML")
    try:
        buf = await asyncio.to_thread(stats_v2.generate_pvp_bioweapons_poster)
        input_file = BufferedInputFile(buf.getvalue(), filename="stats_pvp.png")
        await message.reply_photo(
            photo=input_file,
            caption="⚔️ <b>ТГАЧ Войны Дебаффов, Оружие и Броня</b>",
            parse_mode="HTML",
            reply_markup=build_poster_nav_keyboard("pvp")
        )
        try: await status_msg.delete()
        except Exception: pass
    except Exception as e:
        logger.exception("Error in cmd_pvp_direct: %s", e)
        await status_msg.edit_text(f"⚠️ Ошибка: {e}")


# --- 5. Direct Drama / Beefs Commands ---
@router.message(Command("drama_stats", "beefs", "nemesis", "социология", "бифы", "враги", "драма", ignore_case=True, ignore_mention=True))
async def cmd_drama_direct(message: types.Message, **kwargs):
    """Direct command for Drama / Beefs HD poster."""
    status_msg = await message.reply("⏳ <i>Рендерю карту драмы и вражды...</i>", parse_mode="HTML")
    try:
        buf = await asyncio.to_thread(stats_v2.generate_drama_beef_poster)
        input_file = BufferedInputFile(buf.getvalue(), filename="stats_drama.png")
        await message.reply_photo(
            photo=input_file,
            caption="🧠 <b>ТГАЧ Социология, Бифы и Карта Драмы</b>",
            parse_mode="HTML",
            reply_markup=build_poster_nav_keyboard("drama")
        )
        try: await status_msg.delete()
        except Exception: pass
    except Exception as e:
        logger.exception("Error in cmd_drama_direct: %s", e)
        await status_msg.edit_text(f"⚠️ Ошибка: {e}")


# --- 6. Direct Memes / Bayanometer Commands ---
@router.message(Command("memes_stats", "bayan", "bayans", "баяны", "баян", "мемы", ignore_case=True, ignore_mention=True))
async def cmd_memes_direct(message: types.Message, **kwargs):
    """Direct command for Bayanometer HD poster."""
    status_msg = await message.reply("⏳ <i>Рендерю баянометр и карту мемов...</i>", parse_mode="HTML")
    try:
        buf = await asyncio.to_thread(stats_v2.generate_bayan_memetics_poster)
        input_file = BufferedInputFile(buf.getvalue(), filename="stats_memes.png")
        await message.reply_photo(
            photo=input_file,
            caption="🖼️ <b>ТГАЧ Баянометр, Вирусы и Сленг</b>",
            parse_mode="HTML",
            reply_markup=build_poster_nav_keyboard("memes")
        )
        try: await status_msg.delete()
        except Exception: pass
    except Exception as e:
        logger.exception("Error in cmd_memes_direct: %s", e)
        await status_msg.edit_text(f"⚠️ Ошибка: {e}")


# --- 7. Full Inline Callback Matrix ---
@router.callback_query(F.data.startswith("shub:"))
async def on_stats_v2_callback(callback: types.CallbackQuery, board_id: str | None = None, **kwargs):
    """Handles all interactive category button clicks."""
    action = callback.data.split(":")[1]
    
    if action == "refresh" or action == "home":
        await callback.answer("🔄 Обновляю пульс...")
        text, _ = await asyncio.to_thread(stats_v2.generate_instant_snapshot_text, board_id=board_id)
        try:
            if callback.message:
                if callback.message.photo:
                    await callback.message.delete()
                    await callback.message.answer(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=build_stats_hub_keyboard(),
                        disable_web_page_preview=True
                    )
                else:
                    await callback.message.edit_text(
                        text=text,
                        parse_mode="HTML",
                        reply_markup=build_stats_hub_keyboard(),
                        disable_web_page_preview=True
                    )
        except Exception as e:
            logger.debug("Edit message skipped: %s", e)
        return

    if action == "wrapped":
        await callback.answer("🎴 Рендерю твой Wrapped...")
        user_id = callback.from_user.id
        try:
            buf = await asyncio.to_thread(my_wrapped_generator.generate_my_wrapped_poster, user_id)
            input_file = BufferedInputFile(buf.getvalue(), filename=f"wrapped_{user_id}.png")
            if callback.message:
                await callback.message.answer_photo(
                    photo=input_file,
                    caption="🎴 <b>Твой персональный ТГАЧ Wrapped</b>",
                    parse_mode="HTML",
                    reply_markup=build_poster_nav_keyboard("wrapped")
                )
        except Exception as e:
            logger.exception("Error rendering wrapped callback: %s", e)
            await callback.answer(f"Ошибка: {e}", show_alert=True)
        return

    generator_map = {
        "economy": (stats_v2.generate_economy_heists_poster, "💰 <b>HD-Срез: Экономика, Казино и Криминал</b>"),
        "pvp": (stats_v2.generate_pvp_bioweapons_poster, "⚔️ <b>HD-Срез: Войны Дебаффов, Оружие и Броня</b>"),
        "drama": (stats_v2.generate_drama_beef_poster, "🧠 <b>HD-Срез: Социология, Бифы и Карта Драмы</b>"),
        "memes": (stats_v2.generate_bayan_memetics_poster, "🖼️ <b>HD-Срез: Баянометр, Вирусы и Сленг</b>")
    }

    if action in generator_map:
        func, caption = generator_map[action]
        await callback.answer("🎨 Рендерю HD-постер (1-2 сек)...")
        try:
            buf = await asyncio.to_thread(func)
            input_file = BufferedInputFile(buf.getvalue(), filename=f"stats_{action}.png")
            if callback.message:
                await callback.message.answer_photo(
                    photo=input_file,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=build_poster_nav_keyboard(action)
                )
        except Exception as e:
            logger.exception("Error in poster callback %s: %s", action, e)
            await callback.answer(f"Ошибка генерации: {e}", show_alert=True)
        return
