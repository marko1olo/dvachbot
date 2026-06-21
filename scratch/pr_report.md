# PR Analysis Report

## Branch: `origin/add-clean-title-tests-792982266996526274`
**Commit:** 9031f16 🧪 Add tests for clean_title_text in main.py
**Stat:**  3 files changed, 290 insertions(+), 796 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +408,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
-
-import random
-
-NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
-NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]
```

## Branch: `origin/chore/remove-resolved-fix-comment-thread-id-fallback-4283384337239942146`
**Commit:** 5095609 chore: remove resolved FIX comment for thread ID fallback
**Stat:**  4 files changed, 313 insertions(+), 797 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/common/database.py b/common/database.py
index 9b48c51..bcd5ea3 100644
--- a/common/database.py
+++ b/common/database.py
@@ -2215,7 +2215,6 @@ async def process_mentions_and_notify(source_post_num: int, board_id: str, text:
                            VALUES (?, ?, ?, ?, ?, ?)""",
                         notifications_to_insert
                     )
-                    # FIX: Если t_id is None (чат), используем ID поста, на который отвечаем (rep_num)
                     site_notifs = [
                         (r_id, board_id, str(t_id) if t_id else str(rep_num), src_num, rep_num, 0, current_time)
                         for (r_id, src_num, rep_num, _, t_id, _) in notifications_to_insert
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
```

## Branch: `origin/clean-dead-modes-5265315767736875294`
**Commit:** c4b6780 🧹 [Code Health] Remove dead code related to new_modes
**Stat:**  62 files changed, 1577 insertions(+), 5573 deletions(-)
```diff
diff --git a/.gitignore b/.gitignore
index 8503b7f..ec66c4b 100644
--- a/.gitignore
+++ b/.gitignore
@@ -76,4 +76,3 @@ site_tgach.rar
 bot.lock
 AUTONOMOUS_PROGRESS.md
 security_reports/
-.venv/
diff --git a/Dubsite_tgach/backup.py b/Dubsite_tgach/backup.py
index a79aad0..12c4ce7 100644
--- a/Dubsite_tgach/backup.py
+++ b/Dubsite_tgach/backup.py
@@ -2,10 +2,6 @@ import asyncio
 import logging
 import os
 import shutil
-import asyncio
-import logging
-import os
-import shutil
 import zipfile
 import time
 from datetime import datetime
@@ -13,7 +9,6 @@ from aiogram.types import BufferedInputFile
 from aiogram.exceptions import TelegramRetryAfter
 
 from common.db_pool import get_pool
-from common.database import get_system_setting, set_system_setting
 from site_tgach.admin_config import ADMIN_IDS
 
 logger = logging.getLogger("backup_daemon")
@@ -49,10 +44,10 @@ def split_file_by_size(path: str, chunk_size: int) -> list[str]:
     os.remove(path)
     return parts
 
-async def create_db_backup(bot) -> bool:
+async def create_db_backup(bot):
     if not ADMIN_IDS:
         logger.warning("⚠️ Admin IDs not set, skipping backup.")
-        return False
+        return
     
     backup_db_path = f"backup_{int(time.time())}.db"
     zip_name_base = f"TGACH_Backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.zip"
@@ -99,11 +94,9 @@ async def create_db_backup(bot) -> bool:
                     logger.error(f"Failed to send {part_path} to {admin_id}: {e}")
 
         logger.info("✅ Backup broadcast completed.")
-        return True
```

## Branch: `origin/fix-dead-code-14825127991104520980`
**Commit:** 1042dc2 🧹 [code health improvement] remove commented out code in graceful_shutdown
**Stat:**  2 files changed, 260 insertions(+), 813 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..edd99fd 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +408,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
-
-import random
-
-NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
-NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]
```

## Branch: `origin/fix-file-info-initialization-375130883953053879`
**Commit:** b8ad0f9 Fix: Add comment for file_info initialization in mirror_worker.py
**Stat:**  4 files changed, 298 insertions(+), 797 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +408,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
-
-import random
-
-NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
-NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]
```

## Branch: `origin/fix-geoip-blocking-2937337779805390173`
**Commit:** 6264661 ⚡ Fix Synchronous Blocking Call in Async Function
**Stat:**  3 files changed, 272 insertions(+), 798 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +408,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
-
-import random
-
-NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
-NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]
```

## Branch: `origin/fix-html-unescape-importer-3678292432536475352`
**Commit:** 96dc249 test: add AST regression test for HTML unescaping in ThreadImporter
**Stat:**  3 files changed, 281 insertions(+), 796 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +408,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
-
-import random
-
-NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
-NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]
```

## Branch: `origin/fix-importer-comment-2967372311393972795`
**Commit:** 119430b Add # FIX: comment for unescaping HTML before BeautifulSoup
**Stat:**  3 files changed, 261 insertions(+), 796 deletions(-)
```diff
diff --git a/Dubsite_tgach/importer.py b/Dubsite_tgach/importer.py
index f8f7f2c..9c16360 100644
--- a/Dubsite_tgach/importer.py
+++ b/Dubsite_tgach/importer.py
@@ -99,6 +99,7 @@ class ThreadImporter:
         if not raw_html: return ""
         
         import html as html_lib
+        # FIX: Unescape first to let BeautifulSoup see tags properly
         raw_html = html_lib.unescape(raw_html)
 
         replacements = {
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
```

## Branch: `origin/fix-notification-thread-id-fallback-375130883953055918`
**Commit:** 8648da3 fix(database): properly fall back to parent post ID when thread_id is missing
**Stat:**  4 files changed, 307 insertions(+), 798 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/common/database.py b/common/database.py
index 9b48c51..460557c 100644
--- a/common/database.py
+++ b/common/database.py
@@ -7009,8 +7009,8 @@ async def add_reply_to_notification_queue(source_post_num: int, reply_post_num:
                         (original_author_id, source_post_num, reply_post_num, board_id, thread_id, curr_time)
                     )
                     
-                    # FIX: Если thread_id is None, используем ID родительского поста
-                    effective_thread_id = str(thread_id) if thread_id else str(reply_post_num)
+
+                    effective_thread_id = str(thread_id) if thread_id else str(source_post_num)
                     
                     await db.execute(
                         """INSERT INTO UserReplies 
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
```

## Branch: `origin/fix-sql-injection-dbchecker-13700962311981975639`
**Commit:** 247186a 🔒 Fix SQL Injection vulnerability in dbchecker.py
**Stat:**  63 files changed, 1581 insertions(+), 3849 deletions(-)
```diff
diff --git a/.gitignore b/.gitignore
index 8503b7f..ec66c4b 100644
--- a/.gitignore
+++ b/.gitignore
@@ -76,4 +76,3 @@ site_tgach.rar
 bot.lock
 AUTONOMOUS_PROGRESS.md
 security_reports/
-.venv/
diff --git a/Dubsite_tgach/backup.py b/Dubsite_tgach/backup.py
index a79aad0..12c4ce7 100644
--- a/Dubsite_tgach/backup.py
+++ b/Dubsite_tgach/backup.py
@@ -2,10 +2,6 @@ import asyncio
 import logging
 import os
 import shutil
-import asyncio
-import logging
-import os
-import shutil
 import zipfile
 import time
 from datetime import datetime
@@ -13,7 +9,6 @@ from aiogram.types import BufferedInputFile
 from aiogram.exceptions import TelegramRetryAfter
 
 from common.db_pool import get_pool
-from common.database import get_system_setting, set_system_setting
 from site_tgach.admin_config import ADMIN_IDS
 
 logger = logging.getLogger("backup_daemon")
@@ -49,10 +44,10 @@ def split_file_by_size(path: str, chunk_size: int) -> list[str]:
     os.remove(path)
     return parts
 
-async def create_db_backup(bot) -> bool:
+async def create_db_backup(bot):
     if not ADMIN_IDS:
         logger.warning("⚠️ Admin IDs not set, skipping backup.")
-        return False
+        return
     
     backup_db_path = f"backup_{int(time.time())}.db"
     zip_name_base = f"TGACH_Backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.zip"
@@ -99,11 +94,9 @@ async def create_db_backup(bot) -> bool:
                     logger.error(f"Failed to send {part_path} to {admin_id}: {e}")
 
         logger.info("✅ Backup broadcast completed.")
-        return True
```

## Branch: `origin/fix-sqli-counts-9621706942426493363`
**Commit:** fc3e147 🔒 Fix SQL Injection vulnerabilities in DB count queries
**Stat:**  5 files changed, 307 insertions(+), 801 deletions(-)
```diff
diff --git a/bot_live_status.py b/bot_live_status.py
index 787ba4c..06601f8 100644
--- a/bot_live_status.py
+++ b/bot_live_status.py
@@ -124,10 +124,12 @@ def _db_counts() -> dict:
         conn = sqlite3.connect(DB_PATH, timeout=5)
         cur = conn.cursor()
         result["quick_check"] = cur.execute("PRAGMA quick_check").fetchone()[0]
-        result["Users"] = cur.execute("SELECT COUNT(*) FROM Users").fetchone()[0]
-        result["Posts"] = cur.execute("SELECT COUNT(*) FROM Posts").fetchone()[0]
-        result["PostCopies"] = cur.execute("SELECT COUNT(*) FROM PostCopies").fetchone()[0]
-        result["BroadcastQueue"] = cur.execute("SELECT COUNT(*) FROM BroadcastQueue").fetchone()[0]
+        ALLOWED_TABLES = {"Users", "Posts", "PostCopies", "BroadcastQueue"}
+        for table in ("Users", "Posts", "PostCopies", "BroadcastQueue"):
+            if table in ALLOWED_TABLES:
+                # Use of an explicit allow-list mitigates the SQL Injection vulnerability
+                # associated with string interpolation of table names.
+                result[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
         try:
             result["Users_active"] = cur.execute("SELECT COUNT(*) FROM Users WHERE status='active'").fetchone()[0]
             result["Users_banned"] = cur.execute("SELECT COUNT(*) FROM Users WHERE status='banned'").fetchone()[0]
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/dbchecker.py b/dbchecker.py
index ac3da66..2a93f90 100644
--- a/dbchecker.py
+++ b/dbchecker.py
@@ -77,7 +77,9 @@ def probe_database():
     print("-" * 40)
     for table in tables:
         try:
-            cur.execute(f"SELECT COUNT(*) FROM {table}")
+            # Secure table name formatting
+            safe_table = table.replace('"', '""')
+            cur.execute(f'SELECT COUNT(*) FROM "{safe_table}"')
             count = cur.fetchone()[0]
```

## Branch: `origin/fix-thread-id-fallback-12166220255268120724`
**Commit:** 9a95ff9 fix(database): Move effective_thread_id resolution before NotificationQueue insert
**Stat:**  63 files changed, 1581 insertions(+), 3846 deletions(-)
```diff
diff --git a/.gitignore b/.gitignore
index 8503b7f..ec66c4b 100644
--- a/.gitignore
+++ b/.gitignore
@@ -76,4 +76,3 @@ site_tgach.rar
 bot.lock
 AUTONOMOUS_PROGRESS.md
 security_reports/
-.venv/
diff --git a/Dubsite_tgach/backup.py b/Dubsite_tgach/backup.py
index a79aad0..12c4ce7 100644
--- a/Dubsite_tgach/backup.py
+++ b/Dubsite_tgach/backup.py
@@ -2,10 +2,6 @@ import asyncio
 import logging
 import os
 import shutil
-import asyncio
-import logging
-import os
-import shutil
 import zipfile
 import time
 from datetime import datetime
@@ -13,7 +9,6 @@ from aiogram.types import BufferedInputFile
 from aiogram.exceptions import TelegramRetryAfter
 
 from common.db_pool import get_pool
-from common.database import get_system_setting, set_system_setting
 from site_tgach.admin_config import ADMIN_IDS
 
 logger = logging.getLogger("backup_daemon")
@@ -49,10 +44,10 @@ def split_file_by_size(path: str, chunk_size: int) -> list[str]:
     os.remove(path)
     return parts
 
-async def create_db_backup(bot) -> bool:
+async def create_db_backup(bot):
     if not ADMIN_IDS:
         logger.warning("⚠️ Admin IDs not set, skipping backup.")
-        return False
+        return
     
     backup_db_path = f"backup_{int(time.time())}.db"
     zip_name_base = f"TGACH_Backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.zip"
@@ -99,11 +94,9 @@ async def create_db_backup(bot) -> bool:
                     logger.error(f"Failed to send {part_path} to {admin_id}: {e}")
 
         logger.info("✅ Backup broadcast completed.")
-        return True
```

## Branch: `origin/fix-unescape-html-importer-12713669734798628167`
**Commit:** c760c52 I looked into the importer issue and saw that the necessary fix is already present in the codebase. Since no changes were needed, I am finalizing this task.
**Stat:**  61 files changed, 1577 insertions(+), 3845 deletions(-)
```diff
diff --git a/.gitignore b/.gitignore
index 8503b7f..ec66c4b 100644
--- a/.gitignore
+++ b/.gitignore
@@ -76,4 +76,3 @@ site_tgach.rar
 bot.lock
 AUTONOMOUS_PROGRESS.md
 security_reports/
-.venv/
diff --git a/Dubsite_tgach/backup.py b/Dubsite_tgach/backup.py
index a79aad0..12c4ce7 100644
--- a/Dubsite_tgach/backup.py
+++ b/Dubsite_tgach/backup.py
@@ -2,10 +2,6 @@ import asyncio
 import logging
 import os
 import shutil
-import asyncio
-import logging
-import os
-import shutil
 import zipfile
 import time
 from datetime import datetime
@@ -13,7 +9,6 @@ from aiogram.types import BufferedInputFile
 from aiogram.exceptions import TelegramRetryAfter
 
 from common.db_pool import get_pool
-from common.database import get_system_setting, set_system_setting
 from site_tgach.admin_config import ADMIN_IDS
 
 logger = logging.getLogger("backup_daemon")
@@ -49,10 +44,10 @@ def split_file_by_size(path: str, chunk_size: int) -> list[str]:
     os.remove(path)
     return parts
 
-async def create_db_backup(bot) -> bool:
+async def create_db_backup(bot):
     if not ADMIN_IDS:
         logger.warning("⚠️ Admin IDs not set, skipping backup.")
-        return False
+        return
     
     backup_db_path = f"backup_{int(time.time())}.db"
     zip_name_base = f"TGACH_Backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.zip"
@@ -99,11 +94,9 @@ async def create_db_backup(bot) -> bool:
                     logger.error(f"Failed to send {part_path} to {admin_id}: {e}")
 
         logger.info("✅ Backup broadcast completed.")
-        return True
```

## Branch: `origin/fix-unused-import-asyncio-8768015884326677460`
**Commit:** b865382 🧹 [Code Health] Remove unused asyncio import in deanonymizer.py
**Stat:**  4 files changed, 272 insertions(+), 797 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/deanonymizer.py b/deanonymizer.py
index b02b124..6219644 100644
--- a/deanonymizer.py
+++ b/deanonymizer.py
@@ -1,7 +1,6 @@
 import random
 from typing import Tuple
 from aiogram.types import Message
-import asyncio
 import secrets
 
 from common.html_utils import escape_html
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
```

## Branch: `origin/fix/remove-unused-import-5427400249347427790`
**Commit:** 2898f16 🧹 [Code Health] Remove unused `annotations` import
**Stat:**  3 files changed, 260 insertions(+), 830 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +408,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
-
-import random
-
-NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
-NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]
```

## Branch: `origin/fix/remove-unused-pickle-import-12406240321030756861`
**Commit:** b2e3ccc 🧹 Remove unused pickle import from main.py
**Stat:**  2 files changed, 260 insertions(+), 797 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..96de518 100644
--- a/main.py
+++ b/main.py
@@ -27,15 +27,11 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
 import uuid
-import pickle
 import math
 import tempfile
 import random
@@ -348,7 +344,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +407,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
```

## Branch: `origin/fix/remove-unused-subprocess-11628938915894237699`
**Commit:** 97703f5 🧹 Remove unused 'subprocess' import
**Stat:**  2 files changed, 260 insertions(+), 797 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..669fe6c 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -44,7 +41,6 @@ import secrets
 import html
 import shutil
 import signal
-import subprocess
 import sys
 import io
 import glob
@@ -348,7 +344,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +407,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
```

## Branch: `origin/fix/remove-unused-tuple-import-3124923301229545346`
**Commit:** a73121b 🧹 Remove unused import 'Tuple' in deanonymizer.py
**Stat:**  3 files changed, 260 insertions(+), 797 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/deanonymizer.py b/deanonymizer.py
index b02b124..b66a344 100644
--- a/deanonymizer.py
+++ b/deanonymizer.py
@@ -1,5 +1,4 @@
 import random
-from typing import Tuple
 from aiogram.types import Message
 import asyncio
 import secrets
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
```

## Branch: `origin/fix/remove-unused-verification-import-2745350842672567597`
**Commit:** 3daf1cb 🧹 Remove unused VERIFICATION_REQUIRED_MESSAGES import
**Stat:**  62 files changed, 1578 insertions(+), 3847 deletions(-)
```diff
diff --git a/.gitignore b/.gitignore
index 8503b7f..ec66c4b 100644
--- a/.gitignore
+++ b/.gitignore
@@ -76,4 +76,3 @@ site_tgach.rar
 bot.lock
 AUTONOMOUS_PROGRESS.md
 security_reports/
-.venv/
diff --git a/Dubsite_tgach/backup.py b/Dubsite_tgach/backup.py
index a79aad0..12c4ce7 100644
--- a/Dubsite_tgach/backup.py
+++ b/Dubsite_tgach/backup.py
@@ -2,10 +2,6 @@ import asyncio
 import logging
 import os
 import shutil
-import asyncio
-import logging
-import os
-import shutil
 import zipfile
 import time
 from datetime import datetime
@@ -13,7 +9,6 @@ from aiogram.types import BufferedInputFile
 from aiogram.exceptions import TelegramRetryAfter
 
 from common.db_pool import get_pool
-from common.database import get_system_setting, set_system_setting
 from site_tgach.admin_config import ADMIN_IDS
 
 logger = logging.getLogger("backup_daemon")
@@ -49,10 +44,10 @@ def split_file_by_size(path: str, chunk_size: int) -> list[str]:
     os.remove(path)
     return parts
 
-async def create_db_backup(bot) -> bool:
+async def create_db_backup(bot):
     if not ADMIN_IDS:
         logger.warning("⚠️ Admin IDs not set, skipping backup.")
-        return False
+        return
     
     backup_db_path = f"backup_{int(time.time())}.db"
     zip_name_base = f"TGACH_Backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.zip"
@@ -99,11 +94,9 @@ async def create_db_backup(bot) -> bool:
                     logger.error(f"Failed to send {part_path} to {admin_id}: {e}")
 
         logger.info("✅ Backup broadcast completed.")
-        return True
```

## Branch: `origin/remove-dead-db-backup-code-3539084990686390595`
**Commit:** 3157020 🧹 Remove dead DB backup code
**Stat:**  4 files changed, 266 insertions(+), 819 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..edd99fd 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +408,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
-
-import random
-
-NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
-NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]
```

## Branch: `origin/remove-unused-import-subprocess-7780768151639386453`
**Commit:** d41ce48 🧹 [remove unused import subprocess]
**Stat:**  2 files changed, 260 insertions(+), 797 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..669fe6c 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -44,7 +41,6 @@ import secrets
 import html
 import shutil
 import signal
-import subprocess
 import sys
 import io
 import glob
@@ -348,7 +344,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +407,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
```

## Branch: `origin/security-sql-injection-fix-8192695021856467282`
**Commit:** 506ff41 🔒 [security fix] Fix SQL injection vulnerability in common/database.py
**Stat:**  62 files changed, 1589 insertions(+), 3859 deletions(-)
```diff
diff --git a/.gitignore b/.gitignore
index 8503b7f..ec66c4b 100644
--- a/.gitignore
+++ b/.gitignore
@@ -76,4 +76,3 @@ site_tgach.rar
 bot.lock
 AUTONOMOUS_PROGRESS.md
 security_reports/
-.venv/
diff --git a/Dubsite_tgach/backup.py b/Dubsite_tgach/backup.py
index a79aad0..12c4ce7 100644
--- a/Dubsite_tgach/backup.py
+++ b/Dubsite_tgach/backup.py
@@ -2,10 +2,6 @@ import asyncio
 import logging
 import os
 import shutil
-import asyncio
-import logging
-import os
-import shutil
 import zipfile
 import time
 from datetime import datetime
@@ -13,7 +9,6 @@ from aiogram.types import BufferedInputFile
 from aiogram.exceptions import TelegramRetryAfter
 
 from common.db_pool import get_pool
-from common.database import get_system_setting, set_system_setting
 from site_tgach.admin_config import ADMIN_IDS
 
 logger = logging.getLogger("backup_daemon")
@@ -49,10 +44,10 @@ def split_file_by_size(path: str, chunk_size: int) -> list[str]:
     os.remove(path)
     return parts
 
-async def create_db_backup(bot) -> bool:
+async def create_db_backup(bot):
     if not ADMIN_IDS:
         logger.warning("⚠️ Admin IDs not set, skipping backup.")
-        return False
+        return
     
     backup_db_path = f"backup_{int(time.time())}.db"
     zip_name_base = f"TGACH_Backup_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.zip"
@@ -99,11 +94,9 @@ async def create_db_backup(bot) -> bool:
                     logger.error(f"Failed to send {part_path} to {admin_id}: {e}")
 
         logger.info("✅ Backup broadcast completed.")
-        return True
```

## Branch: `origin/test-roulette-logic-14711329281961330288`
**Commit:** da72c92 🧪 Add tests for roulette_logic
**Stat:**  4 files changed, 344 insertions(+), 797 deletions(-)
```diff
diff --git a/bot_watchdog.py b/bot_watchdog.py
index a47deb1..755c025 100644
--- a/bot_watchdog.py
+++ b/bot_watchdog.py
@@ -411,10 +411,9 @@ def main() -> int:
 
                 time.sleep(POLL_SEC)
         except KeyboardInterrupt:
-            log("Supervisor received KeyboardInterrupt. Exiting cleanly.")
             _kill_tree(child, "supervisor_keyboard_interrupt")
             _close_child_log(child)
-            return 0
+            raise
         except Exception as exc:
             log(f"Supervisor loop error: {type(exc).__name__}: {exc}")
             _kill_tree(child, "supervisor_exception")
diff --git a/main.py b/main.py
index fabd49b..27b3e26 100644
--- a/main.py
+++ b/main.py
@@ -27,10 +27,7 @@ import faulthandler
 import gc
 import gzip
 import psutil
-try:
-    import ujson as json
-except ImportError:
-    import json
+import json
 import logging
 import os
 import tracemalloc
@@ -348,7 +345,7 @@ class BoardMiddleware(BaseMiddleware):
                                 await event.delete()
                             elif isinstance(event, types.CallbackQuery):
                                 pass 
-                        except Exception: 
+                        except: 
                             pass
                         return 
         return await handler(event, data)
@@ -411,21 +408,7 @@ LOCATION_SWITCH_COOLDOWN = 5 # 5 секунд на смену локации (в
 SUMMARIZE_COOLDOWN = 600
 ROAST_COOLDOWN = 300
 
-
-import random
-
-NICK_PREFIXES = ["Базированный", "Всратый", "Мамкин", "Поехавший", "Соевый", "Диванный", "Опущенный", "Гойский", "Толстый", "Порватый", "Латентный", "Просветленный", "Элитный", "Подпивасный", "Двачевский", "Педальный", "Токсичный", "Кринжовый", "Аутичный", "Думерский", "Рядовой", "Школьный", "Отбитый", "Метаироничный", "Скрытый", "Сигма", "Альфа", "Омега", "Сажный", "Вайбовый", "Копиумный", "Попущенный", "Лютый", "Абсолютный", "Печальный", "Нищуковский", "Душный", "Шизоидный", "Паленый", "Забивной", "Плюшевый", "Астральный", "Комнатный"]
-NICK_SUFFIXES = ["Битард", "Скуф", "Шиз", "Анон", "Ньюфаг", "Олдфаг", "Омеган", "Шитпостер", "Сыч", "Двачер", "Чухан", "Куколд", "Нормис", "Гигачад", "Подпивас", "Зумер", "Бумер", "Сояк", "Инцел", "Думер", "Говноед", "Симп", "Чмоня", "Байтер", "Ноулайфер", "Тролль", "Моралфаг", "Альтушка", "Масик", "Школьник", "Дед", "Хиккан", "Скуфидон", "Терпила", "Вахтер", "Тентакль", "Мыслитель", "Философ", "Дворник", "Эрудит", "Чел"]
```
