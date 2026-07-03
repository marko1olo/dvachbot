  2917	async def delete_user_posts(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str) -> int:
  2918	    """
  2919	    Массовое удаление постов пользователя за период.
  2920	    Удаляет из БД (с защитой транзакции), RAM, ЛС и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
  2921	    Правильно удаляет целые треды из БД/архивов, если удаляется ОП-пост.
  2922	    """
  2923	    from common.db_pool import get_pool, db_lock  # Локальный импорт
  2924	    try:
  2925	        time_threshold_ts = (datetime.now(UTC) - timedelta(minutes=time_period_minutes)).timestamp()
  2926
  2927	        posts_to_delete_nums = []
  2928	        messages_to_delete_from_api = []
  2929	        channel_messages_to_delete = []
  2930	        threads_to_delete = []
  2931
  2932	        # 1. Чтение данных и Удаление из БД в одной защищенной транзакции
  2933	        async with db_lock:
  2934	            for attempt in range(10):
  2935	                try:
  2936	                    db = await get_pool()
  2937	                    await db.execute("BEGIN IMMEDIATE")
  2938
  2939	                    # Читаем посты пользователя для удаления
  2940	                    query_posts = "SELECT post_num FROM Posts WHERE author_id = ? AND board_id = ? AND timestamp >= ?"
  2941	                    async with db.execute(query_posts, (user_id, board_id, time_threshold_ts)) as cursor:
  2942	                        rows = await cursor.fetchall()
  2943	                    user_posts = [row[0] for row in rows]
  2944
  2945	                    if not user_posts:
  2946	                        await db.execute("COMMIT")
  2947	                        return 0
  2948
  2949	                    posts_to_delete_set = set(user_posts)
  2950
  2951	                    # Проверяем, какие из этих постов являются ОП-постами тредов
  2952	                    for p_num in user_posts:
  2953	                        p_str = str(p_num)
  2954	                        async with db.execute("SELECT thread_id FROM Threads WHERE thread_id = ? OR thread_num = ?", (p_str, p_num)) as cursor:
  2955	                            t_row = await cursor.fetchone()
  2956	                            if t_row:
  2957	                                threads_to_delete.append(t_row[0])
  2958
  2959	                    # Если есть удаляемые треды, выбираем ВСЕ посты этих тредов, чтобы снести их тоже
  2960	                    if threads_to_delete:
  2961	                        for t_id in threads_to_delete:
  2962	                            try: t_id_int = int(t_id)
  2963	                            except ValueError: t_id_int = 0
  2964
  2965	                            async with db.execute("SELECT post_num FROM Posts WHERE thread_id = ? OR thread_id = ?", (t_id, str(t_id_int))) as cursor:
  2966	                                p_rows = await cursor.fetchall()
  2967	                                for pr in p_rows:
  2968	                                    posts_to_delete_set.add(pr[0])
  2969
  2970	                    posts_to_delete_nums = list(posts_to_delete_set)
  2971	                    placeholders = ','.join('?' for _ in posts_to_delete_nums)
  2972
  2973	                    # Читаем копии для API с получением board_id
  2974	                    query_copies = f"""
  2975	                        SELECT pc.recipient_id, pc.message_id, p.board_id
  2976	                        FROM PostCopies pc
  2977	                        JOIN Posts p ON pc.post_num = p.post_num
  2978	                        WHERE pc.post_num IN ({placeholders})
  2979	                    """
  2980	                    async with db.execute(query_copies, posts_to_delete_nums) as cursor:
  2981	                        messages_to_delete_from_api = await cursor.fetchall()
  2982
  2983	                    # Читаем копии каналов с получением board_id
  2984	                    query_channels = f"""
  2985	                        SELECT cc.channel_id, cc.message_id, p.board_id
  2986	                        FROM ChannelCopies cc
  2987	                        JOIN Posts p ON cc.post_num = p.post_num
  2988	                        WHERE cc.post_num IN ({placeholders})
  2989	                    """
  2990	                    async with db.execute(query_channels, posts_to_delete_nums) as cursor:
  2991	                        channel_messages_to_delete = await cursor.fetchall()
  2992
  2993	                    # Удаляем из Posts
  2994	                    await db.execute(f"DELETE FROM Posts WHERE post_num IN ({placeholders})", posts_to_delete_nums)
  2995
  2996	                    # Удаляем из PostCopies
  2997	                    await db.execute(f"DELETE FROM PostCopies WHERE post_num IN ({placeholders})", posts_to_delete_nums)
  2998
  2999	                    # Удаляем из ChannelCopies
  3000	                    await db.execute(f"DELETE FROM ChannelCopies WHERE post_num IN ({placeholders})", posts_to_delete_nums)
  3001
  3002	                    # Удаляем из UserReplies
  3003	                    await db.execute(f"DELETE FROM UserReplies WHERE post_num IN ({placeholders}) OR parent_num IN ({placeholders})", posts_to_delete_nums + posts_to_delete_nums)
  3004
  3005	                    # Удаляем из Threads
  3006	                    if threads_to_delete:
  3007	                        t_placeholders = ','.join('?' for _ in threads_to_delete)
  3008	                        await db.execute(f"DELETE FROM Threads WHERE thread_id IN ({t_placeholders})", threads_to_delete)
  3009
  3010	                    await db.execute("COMMIT")
  3011	                    break # Успех
  3012
  3013	                except Exception as e:
  3014	                    try: await db.execute("ROLLBACK")
  3015	                    except Exception: pass
  3016
  3017	                    if "locked" in str(e).lower() or "busy" in str(e).lower():
  3018	                        await asyncio.sleep(0.2 * (attempt + 1))
  3019	                        continue
  3020	                    print(f"⛔ DB Error in delete_user_posts: {e}")
  3021	                    return 0
  3022
  3023	        # 2. Чистка RAM (Messages Storage)
  3024	        async with storage_lock:
  3025	            for post_num in posts_to_delete_nums:
  3026	                post_data = messages_storage.pop(post_num, None)
  3027	                if post_data:
  3028	                    if board_id in THREAD_BOARDS:
  3029	                        thread_id = post_data.get('thread_id')
  3030	                        if thread_id:
  3031	                            b_data = board_data.get(board_id, {})
  3032	                            threads_data = b_data.get('threads_data', {})
  3033	                            if thread_id in threads_data:
  3034	                                try:
  3035	                                    if 'posts' in threads_data[thread_id]:
  3036	                                        threads_data[thread_id]['posts'].remove(post_num)
  3037	                                except (ValueError, KeyError):
  3038	                                    pass
  3039	                message_copies_in_mem = post_to_messages.pop(post_num, {})
  3040	                for uid, mid_or_list in message_copies_in_mem.items():
  3041	                    if isinstance(mid_or_list, list):
  3042	                        for mid in mid_or_list:
  3043	                            message_to_post.pop((uid, mid), None)
  3044	                    else:
  3045	                        message_to_post.pop((uid, mid_or_list), None)
  3046
  3047	        # 3. Чистка кэшей
  3048	        from common.database import _THREAD_CACHE, _VIDEO_CACHE, _IMAGE_CACHE
  3049	        for post_id_int in posts_to_delete_nums:
  3050	            post_id_str = str(post_id_int)
  3051	            for b in list(_THREAD_CACHE.keys()):
  3052	                if post_id_str in _THREAD_CACHE[b]:
  3053	                    try: _THREAD_CACHE[b].remove(post_id_str)
  3054	                    except: pass
  3055	            for b in list(_VIDEO_CACHE.keys()):
  3056	                _VIDEO_CACHE[b] = [item for item in _VIDEO_CACHE[b] if item[0] != post_id_int]
  3057	            for b in list(_IMAGE_CACHE.keys()):
  3058	                _IMAGE_CACHE[b] = [item for item in _IMAGE_CACHE[b] if item[0] != post_id_int]
  3059
  3060	        # 4. Удаление из каналов
  3061	        if channel_messages_to_delete:
  3062	            archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
  3063	            for chan_id, msg_id, b_id in channel_messages_to_delete:
  3064	                deleter = archive_bot if archive_bot else (GLOBAL_BOTS.get(b_id) or bot_instance)
  3065	                try:
  3066	                    await deleter.delete_message(chat_id=chan_id, message_id=msg_id)
  3067	                except Exception:
  3068	                    pass
  3069
  3070	        # 5. Удаление из ЛС пользователей (API)
  3071	        async def _delete_one_message(uid: int, mid: int, b_id: str) -> bool:
  3072	            deleter = GLOBAL_BOTS.get(b_id) or bot_instance
  3073	            max_attempts = 6
  3074	            delay = 1.5
  3075	            for attempt in range(max_attempts):
  3076	                try:
  3077	                    await deleter.delete_message(uid, mid)
  3078	                    return True
  3079	                except (TelegramBadRequest, TelegramForbiddenError):
  3080	                    # Если первый бот не имеет доступа, пробуем через bot_instance
  3081	                    if deleter != bot_instance:
  3082	                        try:
  3083	                            await bot_instance.delete_message(uid, mid)
  3084	                            return True
  3085	                        except Exception:
  3086	                            pass
  3087	                    # Пробуем вообще всеми активными ботами по очереди
  3088	                    for other_bid, other_bot in GLOBAL_BOTS.items():
  3089	                        if other_bot != deleter and other_bot != bot_instance:
  3090	                            try:
  3091	                                await other_bot.delete_message(uid, mid)
  3092	                                return True
  3093	                            except Exception:
  3094	                                pass
  3095	                    return False
  3096	                except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError, aiohttp.ClientOSError):
  3097	                    if attempt < max_attempts - 1:
  3098	                        await asyncio.sleep(delay)
  3099	                        delay = min(delay * 2, 30)
  3100	                    else:
  3101	                        return False
  3102	                except Exception:
  3103	                    return False
  3104	            return False
  3105
  3106	        CHUNK_SIZE = 47
  3107	        DELAY_BETWEEN_CHUNKS = 0.11
  3108	        total_deleted_count = 0
  3109
  3110	        for i in range(0, len(messages_to_delete_from_api), CHUNK_SIZE):
  3111	            chunk = messages_to_delete_from_api[i:i + CHUNK_SIZE]
  3112	            tasks = [_delete_one_message(uid, mid, b_id) for uid, mid, b_id in chunk]
  3113	            results = await asyncio.gather(*tasks)
  3114	            total_deleted_count += sum(1 for res in results if res is True)
  3115	            if i + CHUNK_SIZE < len(messages_to_delete_from_api):
  3116	                await asyncio.sleep(DELAY_BETWEEN_CHUNKS)
  3117
  3118	        return total_deleted_count
  3119	    except Exception as e:
  3120	        import traceback
  3121	        print(f"Критическая ошибка в delete_user_posts: {e}\n{traceback.format_exc()}")
  3122	        return 0
