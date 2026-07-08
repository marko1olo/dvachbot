async def delete_user_posts(bot_instance: Bot, user_id: int, time_period_minutes: int, board_id: str) -> int:
      """
      Массовое удаление постов пользователя за период.
      Удаляет из БД (с защитой транзакции), RAM, ЛС и ВСЕХ ЗЕРКАЛ КАНАЛОВ.
      Правильно удаляет целые треды из БД/архивов, если удаляется ОП-пост.
      """
      from common.db_pool import get_pool, db_lock  # Локальный импорт
      try:
          time_threshold_ts = (datetime.now(UTC) - timedelta(minutes=time_period_minutes)).timestamp()

          posts_to_delete_nums = []
          messages_to_delete_from_api = []
          channel_messages_to_delete = []
          threads_to_delete = []

          # 1. Чтение данных и Удаление из БД в одной защищенной транзакции
          async with db_lock:
              for attempt in range(10):
                  try:
                      db = await get_pool()
                      await db.execute("BEGIN IMMEDIATE")

                      # Читаем посты пользователя для удаления
                      query_posts = "SELECT post_num FROM Posts WHERE author_id = ? AND board_id = ? AND timestamp >= ?"
                      async with db.execute(query_posts, (user_id, board_id, time_threshold_ts)) as cursor:
                          rows = await cursor.fetchall()
                      user_posts = [row[0] for row in rows]

                      if not user_posts:
                          await db.execute("COMMIT")
                          return 0

                      posts_to_delete_set = set(user_posts)

                      if user_posts:
                          await db.execute("CREATE TEMP TABLE _TempUserPosts (post_num INTEGER PRIMARY KEY)")
                          await db.executemany("INSERT OR IGNORE INTO _TempUserPosts (post_num) VALUES (?)", [(p,) for p in user_posts])

                          query = """
                              SELECT thread_id FROM Threads
                              WHERE thread_id IN (SELECT CAST(post_num AS TEXT) FROM _TempUserPosts)
                                 OR thread_num IN (SELECT post_num FROM _TempUserPosts)
                          """
                          async with db.execute(query) as cursor:
                              t_rows = await cursor.fetchall()
                              for t_row in t_rows:
                                  threads_to_delete.append(t_row[0])
                          await db.execute("DROP TABLE _TempUserPosts")

                      if threads_to_delete:
                          t_ids = []
                          for t_id in threads_to_delete:
                              t_ids.append(t_id)
                              try: t_id_int = int(t_id)
                              except ValueError: t_id_int = 0
                              t_ids.append(str(t_id_int))
                          t_ids = list(set(t_ids))

                          await db.execute("CREATE TEMP TABLE _TempThreadsToDel (thread_id TEXT PRIMARY KEY)")
                          await db.executemany("INSERT OR IGNORE INTO _TempThreadsToDel (thread_id) VALUES (?)", [(t,) for t in t_ids])

                          query = "SELECT post_num FROM Posts INNER JOIN _TempThreadsToDel ON Posts.thread_id = _TempThreadsToDel.thread_id"
                          async with db.execute(query) as cursor:
                              p_rows = await cursor.fetchall()
                              for pr in p_rows:
                                  posts_to_delete_set.add(pr[0])

                      posts_to_delete_nums = list(posts_to_delete_set)
                      messages_to_delete_from_api = []
                      channel_messages_to_delete = []

                      if posts_to_delete_nums:
                          await db.execute("CREATE TEMP TABLE _TempPostsToDel (post_num INTEGER PRIMARY KEY)")
                          await db.executemany("INSERT OR IGNORE INTO _TempPostsToDel (post_num) VALUES (?)", [(p,) for p in posts_to_delete_nums])

                          query_copies = """
                              SELECT pc.recipient_id, pc.message_id, p.board_id
                              FROM PostCopies pc
                              JOIN Posts p ON pc.post_num = p.post_num
                              INNER JOIN _TempPostsToDel t ON pc.post_num = t.post_num
                          """
                          async with db.execute(query_copies) as cursor:
                              messages_to_delete_from_api = await cursor.fetchall()

                          query_channels = """
                              SELECT cc.channel_id, cc.message_id, p.board_id
                              FROM ChannelCopies cc
                              JOIN Posts p ON cc.post_num = p.post_num
                              INNER JOIN _TempPostsToDel t ON cc.post_num = t.post_num
                          """
                          async with db.execute(query_channels) as cursor:
                              channel_messages_to_delete = await cursor.fetchall()

                          await db.execute("DELETE FROM Posts WHERE post_num IN (SELECT post_num FROM _TempPostsToDel)")
                          await db.execute("DELETE FROM PostCopies WHERE post_num IN (SELECT post_num FROM _TempPostsToDel)")
                          await db.execute("DELETE FROM ChannelCopies WHERE post_num IN (SELECT post_num FROM _TempPostsToDel)")
                          await db.execute("DELETE FROM UserReplies WHERE post_num IN (SELECT post_num FROM _TempPostsToDel) OR parent_num IN (SELECT post_num FROM _TempPostsToDel)")

                          await db.execute("DROP TABLE _TempPostsToDel")

                      if threads_to_delete:
                          await db.execute("DELETE FROM Threads WHERE thread_id IN (SELECT thread_id FROM _TempThreadsToDel)")
                          await db.execute("DROP TABLE _TempThreadsToDel")

                      await db.execute("COMMIT")
                      break # Успех

                  except Exception as e:
                      try: await db.execute("ROLLBACK")
                      except Exception: pass

                      if "locked" in str(e).lower() or "busy" in str(e).lower():
                          await asyncio.sleep(0.2 * (attempt + 1))
                          continue
                      print(f"⛔ DB Error in delete_user_posts: {e}")
                      return 0

          # 2. Чистка RAM (Messages Storage)
          async with storage_lock:
              for post_num in posts_to_delete_nums:
                  post_data = messages_storage.pop(post_num, None)
                  if post_data:
                      if board_id in THREAD_BOARDS:
                          thread_id = post_data.get('thread_id')
                          if thread_id:
                              b_data = board_data.get(board_id, {})
                              threads_data = b_data.get('threads_data', {})
                              if thread_id in threads_data:
                                  try:
                                      if 'posts' in threads_data[thread_id]:
                                          threads_data[thread_id]['posts'].remove(post_num)
                                  except (ValueError, KeyError):
                                      pass
                  message_copies_in_mem = post_to_messages.pop(post_num, {})
                  for uid, mid_or_list in message_copies_in_mem.items():
                      if isinstance(mid_or_list, list):
                          for mid in mid_or_list:
                              message_to_post.pop((uid, mid), None)
                      else:
                          message_to_post.pop((uid, mid_or_list), None)

          # 3. Чистка кэшей
          from common.database import _THREAD_CACHE, _VIDEO_CACHE, _IMAGE_CACHE
          for post_id_int in posts_to_delete_nums:
              post_id_str = str(post_id_int)
              for b in list(_THREAD_CACHE.keys()):
                  if post_id_str in _THREAD_CACHE[b]:
                      try: _THREAD_CACHE[b].remove(post_id_str)
                      except: pass
              for b in list(_VIDEO_CACHE.keys()):
                  _VIDEO_CACHE[b] = [item for item in _VIDEO_CACHE[b] if item[0] != post_id_int]
              for b in list(_IMAGE_CACHE.keys()):
                  _IMAGE_CACHE[b] = [item for item in _IMAGE_CACHE[b] if item[0] != post_id_int]

          # 4. Удаление из каналов
          if channel_messages_to_delete:
              archive_bot = GLOBAL_BOTS.get(ARCHIVE_POSTING_BOT_ID)
              for chan_id, msg_id, b_id in channel_messages_to_delete:
                  deleter = archive_bot if archive_bot else (GLOBAL_BOTS.get(b_id) or bot_instance)
                  try:
                      await deleter.delete_message(chat_id=chan_id, message_id=msg_id)
                  except Exception:
                      pass

          # 5. Удаление из ЛС пользователей (API)
          async def _delete_one_message(uid: int, mid: int, b_id: str) -> bool:
              deleter = GLOBAL_BOTS.get(b_id) or bot_instance
              max_attempts = 6
              delay = 1.5
              for attempt in range(max_attempts):
                  try:
                      await deleter.delete_message(uid, mid)
                      return True
                  except (TelegramBadRequest, TelegramForbiddenError):
                      # Если первый бот не имеет доступа, пробуем через bot_instance
                      if deleter != bot_instance:
                          try:
                              await bot_instance.delete_message(uid, mid)
                              return True
                          except Exception:
                              pass
                      # Пробуем вообще всеми активными ботами по очереди
                      for other_bid, other_bot in GLOBAL_BOTS.items():
                          if other_bot != deleter and other_bot != bot_instance:
                              try:
                                  await other_bot.delete_message(uid, mid)
                                  return True
                              except Exception:
                                  pass
                      return False
                  except (TelegramNetworkError, asyncio.TimeoutError, aiohttp.ClientError, aiohttp.ClientOSError):
                      if attempt < max_attempts - 1:
                          await asyncio.sleep(delay)
                          delay = min(delay * 2, 30)
                      else:
                          return False
                  except Exception:
                      return False
              return False

          CHUNK_SIZE = 47
          DELAY_BETWEEN_CHUNKS = 0.11
          total_deleted_count = 0

          for i in range(0, len(messages_to_delete_from_api), CHUNK_SIZE):
              chunk = messages_to_delete_from_api[i:i + CHUNK_SIZE]
              tasks = [_delete_one_message(uid, mid, b_id) for uid, mid, b_id in chunk]
              results = await asyncio.gather(*tasks)
              total_deleted_count += sum(1 for res in results if res is True)
              if i + CHUNK_SIZE < len(messages_to_delete_from_api):
                  await asyncio.sleep(DELAY_BETWEEN_CHUNKS)

          return total_deleted_count
      except Exception as e:
          import traceback
          print(f"Критическая ошибка в delete_user_posts: {e}\n{traceback.format_exc()}")
          return 0
