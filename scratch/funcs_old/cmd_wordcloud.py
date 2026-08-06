@dp.message(Command("wordcloud", "words", "╨╛╨▒╨╗╨░╨║╨╛"))
async def cmd_wordcloud(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")
    
    if not HAS_WORDCLOUD or not GRAPH_LIBS_AVAILABLE:
        await message.answer("Γ¥î ╨Ü╨╛╨╝╨┐╨╛╨╜╨╡╨╜╤é╤ï WordCloud ╨╕╨╗╨╕ Matplotlib ╨╜╨╡ ╤â╤ü╤é╨░╨╜╨╛╨▓╨╗╨╡╨╜╤ï.")
        return
    
    wait_msg = "ΓÅ│ ╨í╨╛╨▒╨╕╤Ç╨░╤Ä ╤ü╨╗╨╛╨▓╨░ ╨╖╨░ ╨┐╨╛╤ü╨╗╨╡╨┤╨╜╨╕╨╡ 24 ╤ç╨░╤ü╨░..."
    if lang == 'en': wait_msg = "ΓÅ│ Gathering words for the last 24 hours..."
    elif lang == 'jp': wait_msg = "ΓÅ│ ΘüÄσÄ╗24µÖéΘûôπü«σìÿΦ¬₧πéÆσÅÄΘ¢åΣ╕¡..."
    
    status_message = await message.answer(wait_msg)
    
    try:
        db = await get_pool()
        
        # 24 hours ago
        target_timestamp = time.time() - 86400
        
        rows = await db.execute(
            "SELECT content FROM Posts WHERE board_id = ? AND timestamp > ?",
            (board_id, target_timestamp)
        )
        posts = await rows.fetchall()
        
        def process_posts(posts_list):
            text_corpus = ""
            for row in posts_list:
                try:
                    content_dict = json.loads(row[0])
                    text = ""
                    if content_dict.get('type') == 'text':
                        text = content_dict.get('text', '')
                    elif content_dict.get('type') in ['photo', 'video', 'animation', 'document']:
                        text = content_dict.get('caption', '')

                    if text:
                        # Remove HTML tags
                        text = re.sub(r'<[^>]+>', ' ', text)
                        # Remove URLs
                        text = re.sub(r'http[s]?://\S+', ' ', text)
                        text_corpus += text + " "
                except Exception:
                    continue

            words = re.findall(r'[╨░-╤Å╨É-╨»a-zA-Z]{3,}', text_corpus.lower())
            return " ".join([w for w in words if w not in STOP_WORDS])

        final_text = await asyncio.to_thread(process_posts, posts)
        
        if not final_text.strip():
            await status_message.edit_text("Γ¥î ╨Ñ╤â╨╣ ╤é╨░╨╝ ╨┐╨╗╨░╨▓╨░╨╗, ╨░ ╨╜╨╡ ╨╛╨▒╨╗╨░╨║╨╛ ╤ü╨╗╨╛╨▓. ╨Æ╤ï ╨╜╨░╤ä╨╗╤â╨┤╨╕╨╗╨╕ ╤ü╨╗╨╕╤ê╨║╨╛╨╝ ╨╝╨░╨╗╨╛ ╤é╨╡╨║╤ü╤é╨░ ╨╖╨░ ╤ü╤â╤é╨║╨╕.")
            return

        def generate_image(txt):
            wc = WordCloud(
                width=1000, height=600, 
                background_color='black', 
                colormap='viridis',
                max_words=150,
                collocations=False
            )
            wc.generate(txt)
            
            img_io = io.BytesIO()
            wc.to_image().save(img_io, 'PNG')
            img_io.seek(0)
            return img_io

        img_io = await asyncio.to_thread(generate_image, final_text)
        
        caption = f"Γÿü∩╕Å <b>╨₧╨▒╨╗╨░╨║╨╛ ╤ü╨╗╨╛╨▓ /{board_id}/ ╨╖╨░ 24 ╤ç╨░╤ü╨░</b>"
        if lang == 'en': caption = f"Γÿü∩╕Å <b>Word Cloud /{board_id}/ (24h)</b>"
        elif lang == 'jp': caption = f"Γÿü∩╕Å <b>πâ»πâ╝πâëπé»πâ⌐πéªπâë /{board_id}/ (24h)</b>"
        
        await message.answer_photo(
            photo=types.BufferedInputFile(img_io.read(), filename="wordcloud.png"),
            caption=caption,
            parse_mode="HTML"
        )
        await status_message.delete()
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        await status_message.edit_text(f"╨ƒ╤Ç╨╛╨╕╨╖╨╛╤ê╨╗╨░ ╨╛╤ê╨╕╨▒╨║╨░ ╨┐╤Ç╨╕ ╨│╨╡╨╜╨╡╤Ç╨░╤å╨╕╨╕ ╨╛╨▒╨╗╨░╨║╨░ ╤ü╨╗╨╛╨▓: {e}", parse_mode=None)