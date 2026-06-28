  2918	async def _delete_user_posts_from_db(user_id: int, time_threshold_ts: float, board_id: str) -> tuple[list[int], list, list]:
  2919	    from common.db_pool import get_pool, db_lock
  2920	    async with db_lock:
  2921	        for attempt in range(10):
  2922	            try:
  2923	                db = await get_pool()
  2924	                await db.execute("BEGIN IMMEDIATE")
  2925
  2926	                query_posts = "SELECT post_num FROM Posts WHERE author_id = ? AND board_id = ? AND timestamp >= ?"
  2927	                async with db.execute(query_posts, (user_id, board_id, time_threshold_ts)) as cursor:
  2928	                    rows = await cursor.fetchall()
  2929	                user_posts = [row[0] for row in rows]
  2930
  2931	                if not user_posts:
  2932	                    await db.execute("COMMIT")
  2933	                    return [], [], []
  2934
  2935	                posts_to_delete_set = set(user_posts)
  2936	                threads_to_delete = []
  2937
  2938	                for p_num in user_posts:
  2939	                    p_str = str(p_num)
  2940	                    async with db.execute("SELECT thread_id FROM Threads WHERE thread_id = ? OR thread_num = ?", (p_str, p_num)) as cursor:
  2941	                        t_row = await cursor.fetchone()
  2942	                        if t_row:
  2943	                            threads_to_delete.append(t_row[0])
  2944
  2945	                if threads_to_delete:
  2946	                    for t_id in threads_to_delete:
  2947	                        try: t_id_int = int(t_id)
  2948	                        except ValueError: t_id_int = 0
  2949	                        async with db.execute("SELECT post_num FROM Posts WHERE thread_id = ? OR thread_id = ?", (t_id, str(t_id_int))) as cursor:
  2950	                            p_rows = await cursor.fetchall()
  2951	                            for pr in p_rows:
  2952	                                posts_to_delete_set.add(pr[0])
  2953
  2954	                posts_to_delete_nums = list(posts_to_delete_set)
  2955	                placeholders = ','.join('?' for _ in posts_to_delete_nums)
  2956
  2957	                query_copies = f"""
  2958	                    SELECT pc.recipient_id, pc.message_id, p.board_id
  2959	                    FROM PostCopies pc
  2960	                    JOIN Posts p ON pc.post_num = p.post_num
  2961	                    WHERE pc.post_num IN ({placeholders})
  2962	                """
  2963	                async with db.execute(query_copies, posts_to_delete_nums) as cursor:
  2964	                    messages_to_delete_from_api = await cursor.fetchall()
  2965
  2966	                query_channels = f"""
  2967	                    SELECT cc.channel_id, cc.message_id, p.board_id
  2968	                    FROM ChannelCopies cc
  2969	                    JOIN Posts p ON cc.post_num = p.post_num
  2970	                    WHERE cc.post_num IN ({placeholders})
  2971	                """
  2972	                async with db.execute(query_channels, posts_to_delete_nums) as cursor:
  2973	                    channel_messages_to_delete = await cursor.fetchall()
  2974
  2975	                await db.execute(f"DELETE FROM Posts WHERE post_num IN ({placeholders})", posts_to_delete_nums)
  2976	                await db.execute(f"DELETE FROM PostCopies WHERE post_num IN ({placeholders})", posts_to_delete_nums)
  2977	                await db.execute(f"DELETE FROM ChannelCopies WHERE post_num IN ({placeholders})", posts_to_delete_nums)
  2978	                await db.execute(f"DELETE FROM UserReplies WHERE post_num IN ({placeholders}) OR parent_num IN ({placeholders})", posts_to_delete_nums + posts_to_delete_nums)
  2979
  2980	                if threads_to_delete:
  2981	                    t_placeholders = ','.join('?' for _ in threads_to_delete)
  2982	                    await db.execute(f"DELETE FROM Threads WHERE thread_id IN ({t_placeholders})", threads_to_delete)
  2983
  2984	                await db.execute("COMMIT")
  2985	                return posts_to_delete_nums, messages_to_delete_from_api, channel_messages_to_delete
  2986
  2987	            except Exception as e:
  2988	                import asyncio
  2989	                try: await db.execute("ROLLBACK")
  2990	                except Exception: pass
  2991	                if "locked" in str(e).lower() or "busy" in str(e).lower():
  2992	                    await asyncio.sleep(0.2 * (attempt + 1))
  2993	                    continue
  2994	                print(f"⛔ DB Error in delete_user_posts: {e}")
  2995	                return [], [], []
  2996	    return [], [], []
  2997
  2998	async def _clean_posts_from_ram(posts_to_delete_nums: list[int], board_id: str):
  2999	    async with storage_lock:
  3000	        for post_num in posts_to_delete_nums:
  3001	            post_data = messages_storage.pop(post_num, None)
  3002	            if post_data:
  3003	                if board_id in THREAD_BOARDS:
  3004	                    thread_id = post_data.get('thread_id')
  3005	                    if thread_id:
  3006	                        b_data = board_data.get(board_id, {})
  3007	                        threads_data = b_data.get('threads_data', {})
  3008	                        if thread_id in threads_data:
  3009	                            try:
  3010	                                if 'posts' in threads_data[thread_id]:
  3011	                                    threads_data[thread_id]['posts'].remove(post_num)
  3012	                            except (ValueError, KeyError):
  3013	                                pass
  3014	            message_copies_in_mem = post_to_messages.pop(post_num, {})
  3015	            for uid, mid_or_list in message_copies_in_mem.items():
  3016	                if isinstance(mid_or_list, list):
  3017	                    for mid in mid_or_list:
  3018	                        message_to_post.pop((uid, mid), None)
  3019	                else:
  3020	                    message_to_post.pop((uid, mid_or_list), None)
  3021
  3022	def _clean_posts_from_caches(posts_to_delete_nums: list[int]):
  3023	    from common.database import _THREAD_CACHE, _VIDEO_CACHE, _IMAGE_CACHE
  3024	    for post_id_int in posts_to_delete_nums:
  3025	        post_id_str = str(post_id_int)
  3026	        for b in list(_THREAD_CACHE.keys()):
  3027	            if post_id_str in _THREAD_CACHE[b]:
  3028	                try: _THREAD_CACHE[b].remove(post_id_str)
  3029	                except: pass
  3030	        for b in list(_VIDEO_CACHE.keys()):
  3031	            _VIDEO_CACHE[b] = [item for item in _VIDEO_CACHE[b] if item[0] != post_id_int]
  3032	        for b in list(_IMAGE_CACHE.keys()):
  3033	            _IMAGE_CACHE[b] = [item for item in _IMAGE_CACHE[b] if item[0] != post_id_int]
  3034
  3035	async def _delete_posts_from_channels(channel_messages_to_delete: list, bot_instance):
  3036	    if not channel_messages_to_delete:
  3037	        return
  3038	    archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
  3039	    for chan_id, msg_id, b_id in channel_messages_to_delete:
  3040	        deleter = archive_bot if archive_bot else (GLOBAL_BOTS.get(b_id) or bot_instance)
  3041	        try:
  3042	            await deleter.delete_message(chat_id=chan_id, message_id=msg_id)
  3043	        except Exception:
  3044	            pass
  3045
  3046	async def _delete_posts_from_pm_api(messages_to_delete_from_api: list, bot_instance) -> int:
  3047	    import asyncio
  3048	    CHUNK_SIZE = 47
  3049	    DELAY_BETWEEN_CHUNKS = 0.11
  3050	    total_deleted_count = 0
  3051	    for i in range(0, len(messages_to_delete_from_api), CHUNK_SIZE):
  3052	        chunk = messages_to_delete_from_api[i:i + CHUNK_SIZE]
  3053	        tasks = [_delete_message_with_retries(bot_instance, uid, mid, b_id) for uid, mid, b_id in chunk]
  3054	        results = await asyncio.gather(*tasks)
  3055	        total_deleted_count += sum(1 for res in results if res is True)
  3056	        if i + CHUNK_SIZE < len(messages_to_delete_from_api):
  3057	            await asyncio.sleep(DELAY_BETWEEN_CHUNKS)
  3058	    return total_deleted_count
  3059
  3060	async def _delete_message_with_retries(bot_instance, uid: int, mid: int, b_id: str = None) -> bool:
  3061	    deleter = GLOBAL_BOTS.get(b_id) or bot_instance if b_id else bot_instance
  3062	    max_attempts = 6
  3063	    delay = 1.5
  3064	    for attempt in range(max_attempts):
  3065	        try:
  3066	            await deleter.delete_message(uid, mid)
  3067	            return True
  3068	        except (TelegramBadRequest, TelegramForbiddenError):
  3069	            if deleter != bot_instance:
  3070	                try:
  3071	                    await bot_instance.delete_message(uid, mid)
  3072	                    return True
  3073	                except Exception:
  3074	                    pass
  3075	            for other_bid, other_bot in GLOBAL_BOTS.items():
  3076	                if other_bot != deleter and other_bot != bot_instance:
  3077	                    try:
  3078	                        await other_bot.delete_message(uid, mid)
  3079	                        return True
  3080	                    except Exception:
  3081	                        pass
  3082	            return False
  3083	        except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError, aiohttp.ClientOSError):
  3084	            if attempt < max_attempts - 1:
  3085	                await asyncio.sleep(delay)
  3086	                delay = min(delay * 2, 30)
  3087	            else:
  3088	                return False
  3089	        except Exception:
  3090	            return False
  3091	    return False
  3092
  3093	async def delete_user_posts(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str) -> int:
  3094	    """
  3095	    Массовое удаление постов пользователя за период.
  3096	    Удаляет из БД (с защитой транзакции), RAM, ЛС и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
  3097	    Правильно удаляет целые треды из БД/архивов, если удаляется ОП-пост.
  3098	    """
  3099	    try:
  3100	        time_threshold_ts = (datetime.now(UTC) - timedelta(minutes=time_period_minutes)).timestamp()
  3101
  3102	        posts_to_delete_nums, messages_to_delete_from_api, channel_messages_to_delete = await _delete_user_posts_from_db(
  3103	            user_id, time_threshold_ts, board_id
  3104	        )
  3105
  3106	        if not posts_to_delete_nums:
  3107	            return 0
  3108
  3109	        await _clean_posts_from_ram(posts_to_delete_nums, board_id)
  3110	        _clean_posts_from_caches(posts_to_delete_nums)
  3111	        await _delete_posts_from_channels(channel_messages_to_delete, bot_instance)
  3112	        total_deleted_count = await _delete_posts_from_pm_api(messages_to_delete_from_api, bot_instance)
  3113
  3114	        return total_deleted_count
  3115	    except Exception as e:
  3116	        import traceback
  3117	        print(f"Критическая ошибка в delete_user_posts: {e}\n{traceback.format_exc()}")
  3118	        return 0
  3119	async def delete_single_post(post_num: int, bot_instance: Bot) -> int:
  3120	    """
  3121	    Удаляет один конкретный пост отовсюду: из БД, RAM, ЛС пользователей и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
  3122	    """
  3123	    from common.db_pool import get_pool
  3124	    board_id = None
  3125	    try:
  3126	        db = await get_pool()
  3127	        async with db.execute("SELECT board_id FROM Posts WHERE post_num = ?", (post_num,)) as cursor:
  3128	            row = await cursor.fetchone()
  3129	            if row:
  3130	                board_id = row[0]
  3131	    except Exception:
  3132	        pass
  3133
  3134	    channel_copies = await get_all_channel_copies(post_num)
  3135	    messages_to_delete_info = await get_post_copies(post_num)
  3136	    deleted_from_db = await delete_post_by_num(post_num)
  3137	    if not deleted_from_db and not messages_to_delete_info and not channel_copies:
  3138	        return 0
  3139	    async with storage_lock:
  3140	        post_data = messages_storage.pop(post_num, None)
  3141	        if post_data:
  3142	            if not board_id:
  3143	                board_id = post_data.get('board_id')
  3144	            if board_id and board_id in THREAD_BOARDS:
  3145	                thread_id = post_data.get('thread_id')
  3146	                if thread_id:
  3147	                    b_data = board_data.get(board_id, {})
  3148	                    threads_data = b_data.get('threads_data', {})
  3149	                    if thread_id in threads_data:
  3150	                        try:
  3151	                            if 'posts' in threads_data[thread_id]:
  3152	                                threads_data[thread_id]['posts'].remove(post_num)
  3153	                        except (ValueError, KeyError):
  3154	                            pass
  3155	        message_copies_in_mem = post_to_messages.pop(post_num, {})
  3156	        for uid, mid_or_list in message_copies_in_mem.items():
  3157	            if isinstance(mid_or_list, list):
  3158	                for mid in mid_or_list:
  3159	                    message_to_post.pop((uid, mid), None)
  3160	            else:
  3161	                message_to_post.pop((uid, mid_or_list), None)
  3162	    if channel_copies:
  3163	        archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
  3164	        deleter = archive_bot if archive_bot else (GLOBAL_BOTS.get(board_id) or bot_instance)
  3165	        for chan_id, msg_id in channel_copies:
  3166	            try:
  3167	                await deleter.delete_message(chat_id=chan_id, message_id=msg_id)
  3168	            except Exception:
  3169	                pass
  3170	    if not messages_to_delete_info:
  3171	        return 0 if deleted_from_db else 0
  3172
  3173	    tasks = [_delete_message_with_retries(bot_instance, uid, mid, board_id) for uid, mid in messages_to_delete_info]
  3174	    results = await asyncio.gather(*tasks)
  3175	    deleted_count = sum(1 for res in results if res is True)
  3176	    return deleted_count
  3177	async def send_moderation_notice(user_id: int, action: str, board_id: str, duration: str = None, deleted_posts: int = 0, stream: str = 'ru'):
