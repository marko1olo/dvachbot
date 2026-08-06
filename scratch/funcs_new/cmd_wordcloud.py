@dp.message(Command("wordcloud", "words", "облако"))
async def cmd_wordcloud(message: types.Message, board_id: str | None, stream: str = 'ru'):
    if not board_id: return
    lang = stream if ENABLE_MULTILANG else ('en' if board_id == 'int' else 'ru')
    
    try: spawn_task(delete_message_after_delay(message, 5))
    except Exception as e: runtime_logger.warning(f"Failed to spawn delete_message task: {e}")
    
    if not HAS_WORDCLOUD or not GRAPH_LIBS_AVAILABLE:
        await message.answer("❌ Компоненты WordCloud или Matplotlib не установлены.")
        return
    
    wait_msg = "⏳ Собираю слова за последние 24 часа..."
    if lang == 'en': wait_msg = "⏳ Gathering words for the last 24 hours..."
    elif lang == 'jp': wait_msg = "⏳ 過去24時間の単語を収集中..."
    
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

            words = re.findall(r'[а-яА-Яa-zA-Z]{3,}', text_corpus.lower())
            return " ".join([w for w in words if w not in STOP_WORDS])

        final_text = await asyncio.to_thread(process_posts, posts)
        
        if not final_text.strip():
            await status_message.edit_text("❌ Хуй там плавал, а не облако слов. Вы нафлудили слишком мало текста за сутки.")
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
        
        caption = f"☁️ <b>Облако слов /{board_id}/ за 24 часа</b>"
        if lang == 'en': caption = f"☁️ <b>Word Cloud /{board_id}/ (24h)</b>"
        elif lang == 'jp': caption = f"☁️ <b>ワードクラウド /{board_id}/ (24h)</b>"
        
        await message.answer_photo(
            photo=types.BufferedInputFile(img_io.read(), filename="wordcloud.png"),
            caption=caption,
            parse_mode="HTML"
        )
        await status_message.delete()
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        await status_message.edit_text(f"Произошла ошибка при генерации облака слов: {e}", parse_mode=None)