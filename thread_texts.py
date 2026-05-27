# thread_texts.py

thread_messages = {
    'ru': {
        # --- Создание треда ---
        'create_usage': [
            "🚫 Хуйню несешь. Пиши: <code>/create &lt;охуенный заголовок треда&gt;</code>", "🚫 Не, так не пойдет. Формат: <code>/create &lt;название тредика&gt;</code>",
            "🚫 Ты че, дебил? Надо <code>/create &lt;заголовок&gt;</code>.", "🚫 Ошибка синтаксиса в твоей башке. Пример: <code>/create Срач про аниме</code>",
            "🚫 Руки из жопы? Команда: <code>/create &lt;текст заголовка&gt;</code>", "🚫 Неверно. Используй: <code>/create &lt;то, о чем твой высер&gt;</code>",
            "🚫 Нет. Нет. Нет. <code>/create &lt;заголовок&gt;</code>. Запомни.", "🚫 Формат-то какой? <code>/create &lt;название&gt;</code>. Понял?",
            "🚫 Ты пропустил самое главное - заголовок. <code>/create ЗАГОЛОВОК</code>", "🚫 Просто напиши <code>/create</code> и дальше название треда. Сложно?",
            "🚫 После команды /create должен идти заголовок твоего треда, еблан.", "🚫 Заголовок где, я спрашиваю? <code>/create НАЗВАНИЕ</code>",
            "🚫 Ты пытаешься создать тред без названия. Гениально. Но нет.", "🚫 Команда, потом пробел, потом название. Заруби на носу.",
            "🚫 /create, а потом название. Не наоборот. Не через жопу.", "🚫 Алло, гараж! <code>/create &lt;заголовок&gt;</code>. Повторяю для тупых.",
            "🚫 Ты забыл суть. <code>/create &lt;СУТЬ&gt;</code>.", "🚫 Мозги включи. <code>/create &lt;название треда&gt;</code>.",
            "🚫 Я не понимаю, чего ты хочешь. Попробуй <code>/create &lt;четкое название&gt;</code>.", "🚫 Сначала /create, потом название. Неужели так трудно?",
        ],

        'create_invalid_input': [
            "🚫 Эй, я жду текст, а не вот это вот всё. Давай ОП-пост.",
            "🚫 Ты прикалываешься? Мне нужен текст для треда, а не стикеры.",
            "🚫 Не, так дело не пойдет. Отправь мне текст, который станет первым постом.",
            "🚫 Ожидается текст. Только текст. Буквы, слова, предложения. Понял?",
            "🚫 Это, конечно, очень смешно, но я жду текст для ОП-поста.",
            "🚫 Тред из картинки? Оригинально, но нет. Давай текст.",
            "🚫 Алло, нужен текст! Что ты мне шлешь?",
            "🚫 Отправь мне нормальный текстовый пост, а не это.",
            "🚫 Текст где? Я не умею читать мысли и стикеры.",
            "🚫 ОП-пост должен быть текстом. Попробуй еще раз.",
        ],
        
        'create_prompt_op_post': [
            "Напиши текст для первого поста (ОП-поста) твоего треда.",
            "Какова тема твоего треда? Отправь текст ОП-поста.",
            "Жду текст для создания нового треда. Удиви меня.",
            "Отправь содержимое первого поста, чтобы начать обсуждение."
        ],
        'create_prompt_op_post_edit': [
            "Хорошо, отправь новый текст для ОП-поста.",
            "Введи исправленный текст заголовка/поста."
        ],
        'create_confirmation': [
            "Тред готов к созданию. Публикуем?",
            "Всё верно? Создаем тред с этим текстом?",
            "Подтверди создание треда."
        ],
        'create_cancelled': [
            "Создание треда отменено. Возвращайся, когда созреешь.",
            "Отмена. Тред не создан.",
            "Операция прервана. Можешь продолжать щитпостить на главной."
        ],
        'create_success': [
            "✅ Оп-па, тред «<b>{title}</b>» вкатился в чат. Залетайте, обсуждайте.", "✅ Создал твой высер «<b>{title}</b>». Не обосрись там.",
            "✅ Тред «<b>{title}</b>» успешно создан. Ждем экспертов.", "✅ Есть пробитие! Тред «<b>{title}</b>» появился на доске.",
            "✅ Тред «<b>{title}</b>» запущен. Теперь можно и посраться.", "✅ Ваша тема «<b>{title}</b>» создана. Не благодарите.",
            "✅ Начинаем новый срач: «<b>{title}</b>». Присоединяйтесь.", "✅ Новый тред «<b>{title}</b>» уже здесь. Врывайтесь.",
            "✅ Done. Тред «<b>{title}</b>» ждет твоих сообщений.", "✅ Запускаю шарманку. Тред «<b>{title}</b>» в эфире.",
            "✅ Тред «<b>{title}</b>» восстал из пепла твоих идей.", "✅ Поехали. Тред «<b>{title}</b>» открыт.",
            "✅ Твой тред «<b>{title}</b>» готов. Зови друзей.", "✅ Зарегистрировал новый тред: «<b>{title}</b>».",
            "✅ Срач под названием «<b>{title}</b>» объявляю открытым.", "✅ Получите, распишитесь: тред «<b>{title}</b>».",
            "✅ Таки создал. «<b>{title}</b>». Наслаждайся.", "✅ Тред «<b>{title}</b>» готов принимать ваши высеры.",
            "✅ «<b>{title}</b>». Запомните это название. Это новый тред.", "✅ Еще один тред. «<b>{title}</b>». Как предсказуемо.",
        ],
        'create_success_with_purge': [
            "✅ Твой тред «<b>{title}</b>» создан. Ради него пришлось смыть в унитаз самый протухший тред «<b>{old_title}</b>».",
            "✅ Создал «<b>{title}</b>». Но доска не резиновая, так что самый заглохший тред «<b>{old_title}</b>» отправился нахуй.",
            "✅ Место под твой высер «<b>{title}</b>» освобождено ценой жизни самого неактивного треда «<b>{old_title}</b>». F.",
            "✅ Поздравляю, «<b>{title}</b>» в эфире. Правда, для этого пришлось пристрелить самый дохлый тред «<b>{old_title}</b>», который давно никто не бампал.",
            "✅ Твой тред «<b>{title}</b>» заменил собой самый унылый и забытый всеми тред «<b>{old_title}</b>». Круговорот дерьма в природе.",
            "✅ Чтобы впихнуть твой «<b>{title}</b>», пришлось выкинуть самый пыльный тред с чердака — «<b>{old_title}</b>».",
            "✅ Есть «<b>{title}</b>»! Но по правилу 'один вошел, один вышел', самый неактивный тред «<b>{old_title}</b>» покинул чат.",
            "✅ Вкатил твой «<b>{title}</b>», но за это пришлось заплатить. Жертвой стал самый непопулярный тред «<b>{old_title}</b>».",
            "✅ Твой тред «<b>{title}</b>» создан. А самый скучный тред «<b>{old_title}</b>» отправлен в утиль.",
            "✅ «<b>{title}</b>» здесь. P.S. Самый мертвый тред «<b>{old_title}</b>» был принесен в жертву богу контента.",
            "✅ Создан «<b>{title}</b>». Одновременно с этим самый позабытый тред «<b>{old_title}</b>» был пущен под нож.",
            "✅ Тред «<b>{title}</b>» занял место почившего треда «<b>{old_title}</b>», который уже никому не был интересен.",
            "✅ Поздравляю с созданием «<b>{title}</b>». Самый заброшенный тред «<b>{old_title}</b>» был удален для освобождения места.",
            "✅ «<b>{title}</b>» врывается на доску, выталкивая своим появлением самый неподвижный тред «<b>{old_title}</b>».",
            "✅ Пришлось провести небольшую чистку. Тред «<b>{old_title}</b>» был удален, чтобы твой «<b>{title}</b>» мог жить. Пользуйся.",
        ],
        'create_cooldown': [
            "⏳ Тормози, ковбой. Новые треды можно раз в {minutes} минут. Жди еще {remaining}.", "⏳ Остынь, графоман. Кулдаун {minutes} минут. Осталось: {remaining}.",
            "⏳ Ты заебал треды клепать. Подожди {remaining}, потом пробуй.", "⏳ Придержи коней. Создавать треды можно раз в {minutes} минут. Осталось {remaining}.",
            "⏳ Не так быстро, спермотоксикозник. Кулдаун {minutes} минут. Жди {remaining}.", "⏳ Ты не пулемет, а я не склад тредов. Отдыхай {remaining}.",
            "⏳ Часто срешь. Лимит: один тред в {minutes} минут. Осталось: {remaining}.", "⏳ Сервер не железный. Пауза {minutes} минут. Тебе ждать {remaining}.",
            "⏳ Прекрати. Просто прекрати. Жди {remaining}.", "⏳ Уймись. Следующий тред через {remaining}.",
            "⏳ Твой конвейер по производству тредов приостановлен. КД {minutes} мин. Осталось: {remaining}.", "⏳ У тебя талант? Нет, у тебя кулдаун. Жди {remaining}.",
            "⏳ Ты думаешь, ты один тут такой умный? Кулдаун. Жди {remaining}.", "⏳ Хватит спамить. Пауза {minutes} минут. Тебе еще {remaining}.",
            "⏳ Перекур {minutes} минут. Не создавай треды так часто. Осталось {remaining}.", "⏳ Завод по производству тредов закрыт на {minutes} минут. Жди {remaining}.",
            "⏳ Поток твоего сознания слишком бурный. Притормози на {remaining}.", "⏳ Ты не фабрика. Кулдаун {minutes} минут. Осталось {remaining}.",
            "⏳ Отдохни. Серьезно. Следующий тред через {remaining}.", "⏳ Ты уже создал тред недавно. Жди {remaining}.",
        ],
        
        'new_thread_public_notification': [
            "🌱 На доске появился новый тред: «<b>{title}</b>». Заходите, пока свежий.",
            "🚨 Внимание, аноны! Открылся новый тред для ваших срачей: «<b>{title}</b>».",
            "✨ На доске запахло свежим контентом. Создан тред «<b>{title}</b>».",
            "📢 Кто-то только что создал новый тред: «<b>{title}</b>». Жми кнопку, чтобы ворваться.",
            "💬 На доске открылся новый тред: «<b>{title}</b>». Го сюда!",
            "📜 Запущен новый тред: «<b>{title}</b>». Приглашаются все желающие.",
            "🔥 Тгачеры! Залетайте в тред «<b>{title}</b>».",
            "🔔 На доске появился новый тред: «<b>{title}</b>». Ждем вашего мнения.",
            "💡 Есть новая тема для разговора: «<b>{title}</b>». Присоединяйтесь!",
            "🆕 Создан новый тред: «<b>{title}</b>». Заходите.",
            "🆕 Внимание! Новый тред: «<b>{title}</b>». Вкатывайтесь.",
        ],
        
        # --- Список тредов ---
        'threads_list_header': [
            "📋 <b>Текущие высеры на доске:</b>", "📋 <b>Активные треды, налетай:</b>", "📋 <b>Список горячих обсуждений:</b>",
            "📋 <b>Вот что сейчас мусолят:</b>", "📋 <b>Срачевник открыт:</b>", "📋 <b>Доска тредов:</b>",
            "📋 <b>Живые треды на данный момент:</b>", "📋 <b>Че каво на доске:</b>", "📋 <b>Актуальные треды:</b>",
            "📋 <b>Смотри, куда можно вкатиться:</b>", "📋 <b>Обсуждения в самом разгаре:</b>", "📋 <b>Список тредов:</b>",
            "📋 <b>Во что можно влезть:</b>", "📋 <b>Актуалочка по тредам:</b>", "📋 <b>Что тут у нас:</b>",
            "📋 <b>Топ тредов на сегодня:</b>", "📋 <b>Свежие треды:</b>", "📋 <b>Куда зайти, о чем поговорить:</b>",
            "📋 <b>Доступные треды:</b>", "📋 <b>Вот они, слева направо:</b>",
        ],
        'threads_list_empty': [
            "Доска пустая, как твоя голова. Создай первый тред.", "Тут пока нет тредов. Будь первым, не ссы.",
            "Ни одного треда. Вообще. Мертвая доска.", "Голяк. Создай тред, стань ОПом.",
            "Пустота. Тишина. Нарушь ее, создай тред.", "Здесь мог бы быть твой тред, но его нет.",
            "Никто ничего не обсуждает. Скука. Создай тред.", "Как в гробу. Ни одного треда.",
            "Начни движуху, создай первый тред.", "Тредов ноль. Абсолютный ноль.",
            "Перекати-поле. Ни одного треда.", "Здесь так тихо, что слышно, как ты дышишь. Создай тред.",
            "Стань легендой. Создай первый тред на этой доске.", "Ни души, ни треда. Твой выход.",
            "Это место ждет своего героя. И своего первого треда.", "Где все? Ау! Тредов нет.",
            "М-да. Пусто. Может, создашь тред?", "Ничего не происходит. Абсолютно. Создай тред.",
            "Похоже, все вымерли. Или просто ждут, пока ты создашь тред.", "Эта доска девственно чиста. Ни одного треда.",
        ],
        'thread_list_item': "{index}. <b>{title}</b> | Постов: {posts_count} | 🕜: {last_activity}",
        
        # --- Вход/Выход/Навигация ---
        'enter_thread_prompt': [
            "Ты в треде «<b>{title}</b>».\n\n📝 Пиши сюда свой бред.\n🚪 Выйти отсюда - /leave.", "Зашел в «<b>{title}</b>».\n\n📝 Сообщения теперь летят сюда.\n🚪 /leave, чтобы свалить.",
            "Окей, ты в «<b>{title}</b>».\n\n📝 Пишешь сюда, выходишь через /leave.", "Добро пожаловать в срач «<b>{title}</b>».\n\n🚪 /leave для побега.",
            "Теперь ты участник треда «<b>{title}</b>».\n\n📝 Неси хуйню прямо здесь.\n🚪 Выход - /leave.", "Ты переключился на тред «<b>{title}</b>».\n\n🚪 Команда /leave вернет тебя обратно.",
            "Локация: тред «<b>{title}</b>».\n\n📝 Все, что напишешь, пойдет сюда. /leave для выхода.", "Ты внутри треда «<b>{title}</b>».\n\n🚪 Чтобы вернуться, используй /leave.",
            "Вход выполнен: «<b>{title}</b>».\n\n📝 Пиши. Чтобы выйти - /leave.", "Погружаемся в «<b>{title}</b>».\n\n🚪 Назад в общую помойку - /leave.",
            "Ты успешно вкатился в тред «<b>{title}</b>».\n\n🚪 Надоест - жми /leave.", "Принят в тред «<b>{title}</b>».\n\n📝 Сри здесь. Выход - /leave.",
            "Ты теперь в этой уютной комнатке: «<b>{title}</b>».\n\n🚪 /leave, чтобы вернуться к быдлу.", "Канал связи перенастроен на тред «<b>{title}</b>».\n\n🚪 /leave для возврата в общий эфир.",
            "Ты присоединился к треду «<b>{title}</b>».\n\n🚪 Для выхода введи /leave.", "Концентрация на треде «<b>{title}</b>».\n\n🚪 /leave, чтобы распылить внимание.",
            "Ты теперь часть треда «<b>{title}</b>».\n\n🚪 /leave, если захочешь стать отшельником.", "Ты в локальном чате треда «<b>{title}</b>».\n\n🚪 Выход - /leave.",
            "Залетаем в «<b>{title}</b>».\n\n🚪 Как выходить, ты знаешь - /leave.", "Ты попал. В тред «<b>{title}</b>».\n\n🚪 /leave, если найдешь выход.",
            "Вы вошли в тред: <b>{title}</b>", "Добро пожаловать в тред: <b>{title}</b>", "Вы перешли в тред: <b>{title}</b>. Общайтесь."
        ],
        'enter_thread_success': [
            "Снова в треде «<b>{title}</b>».", "Ты вернулся в «<b>{title}</b>».", "Опять здесь. Тред «<b>{title}</b>».", "И снова здравствуйте в треде «<b>{title}</b>».",
            "Возвращение в «<b>{title}</b>».", "Ты опять в треде «<b>{title}</b>».", "Снова переключился на «<b>{title}</b>».", "Камбек в «<b>{title}</b>».",
            "Окей, ты в «<b>{title}</b>».", "Ты на месте. Тред «<b>{title}</b>».", "С возвращением в «<b>{title}</b>».", "И снова ты в треде «<b>{title}</b>».",
            "Переключился обратно на «<b>{title}</b>».", "Оп, и ты опять в «<b>{title}</b>».", "Ты снова слушаешь «<b>{title}</b>».", "Снова в этой дыре. «<b>{title}</b>».",
            "Опять этот тред. «<b>{title}</b>».", "Возвращаемся к нашим баранам в «<b>{title}</b>».", "Ты вернулся. «<b>{title}</b>».", "Снова здесь. В треде «<b>{title}</b>».",
            "Вы вернулись в тред: <b>{title}</b>", "С возвращением в тред: <b>{title}</b>", "Продолжаем обсуждение в: <b>{title}</b>"
        ],
        'leave_thread_success': [
            "Свалил из треда. Теперь ты в общем чате.", "Вернулся в общую помойку. Тред позади.", "Окей, ты ливнул. Снова на главной.",
            "Выход из треда выполнен. Ты в общем канале.", "Сбежал. Теперь ты снова в общем чате.", "Ты покинул тред. Возвращаемся к истокам.",
            "Возвращаемся в родную гавань. Ты больше не в треде.", "Тред остался позади. Ты в общем чате.", "Окей, вынырнул. Ты на главной.",
            "Вышел. Снова в общем потоке сознания.", "Ты покинул локальный чат треда.", "Возвращение в общий чат.", "Выход засчитан. Ты на доске.",
            "Больше не в треде. Теперь ты в общем чате.", "Отключился от треда.", "Ты снова со всеми. В общем чате.",
            "Вышел из треда. Добро пожаловать обратно в хаос.", "Покинул тред. Теперь ты слышишь всех.", "Окей, ты снова на общей доске.", "Вышел. Все, как раньше.",
            "Вы вышли из треда на главную доску.", "Возврат на нулевую. Вы покинули тред.", "Вы вышли на главную.", "Тред покинут. Вы снова в общем потоке."
        ],
        'location_switch_cooldown': [
            "⏳ Не так быстро, шило в жопе. Секунду подожди.", "⏳ Эй, полегче. Не кликай так часто.", "⏳ Тормози. Дай серверу отдохнуть.",
            "⏳ Успокойся, флеш. Переключаться можно не так часто.", "⏳ Слишком быстро. Попробуй через пару секунд.", "⏳ Анти-спам защита. Подожди немного.",
            "⏳ Не дёргайся так. Пауза.", "⏳ Ты заебал. Подожди.", "⏳ Хватит скакать туда-сюда. Кулдаун.", "⏳ Перегрев! Остынь.",
            "⏳ Притормози, гонщик.", "⏳ Слишком много переключений. Отдохни.", "⏳ Ты пытаешься сломать бота? Пауза.", "⏳ Не спамь переключениями.",
            "⏳ Я не успеваю. Подожди.", "⏳ Хватит. Просто хватит. Кулдаун.", "⏳ Помедленнее, я записываю. КД.", "⏳ Успокой свой пыл. Подожди.",
            "⏳ Ты слишком суетливый. Жди.", "⏳ Прекрати эту вакханалию. Пауза.", "⏳ Слишком быстро переключаешься. Подожди немного.",
            "⏳ Не скачи по тредам так быстро. Остынь.", "⏳ Подожди пару секунд перед входом/выходом."
        ],
        'thread_not_found': [
            "🚫 Тред сдох или его и не было.", "🚫 Этот тред уже протух и улетел в архив.", "🚫 Хуй тебе, а не тред. Он не найден.",
            "🚫 Такого треда нет. Сорян.", "🚫 Не могу найти этот тред. Возможно, он удален.", "🚫 Проебался тред. Или ты.",
            "🚫 404 Thread Not Found.", "🚫 Этот тред - всё. Финита ля комедия.", "🚫 Похоже, тред отправился к праотцам.",
            "🚫 Нет такого треда. И не было.", "🚫 Искал, искал, не нашел. Тред испарился.", "🚫 Этот тред либо удалили, либо заархивировали. Его нет.",
            "🚫 Ты уверен, что такой тред был? Я не вижу.", "🚫 По этому адресу ничего нет. Тред не найден.", "🚫 Запрашиваемый тред не существует.",
            "🚫 Может, тебе приснилось? Треда нет.", "🚫 Этот тред уже история. В прямом смысле - в архиве.", "🚫 Тред ушел в закат. Его больше нет.",
            "🚫 Не найден. Возможно, опечатка?", "🚫 Нет. Просто нет.", "Тред не найден или удален.",
            "Такого треда больше нет (или не было).", "404: Тред not found.", "Похоже, этот тред утонул в пучине."
        ],
      
        'thread_reaching_bump_limit': [
            "⚠️ Тред «<b>{title}</b>» скоро утонет! Осталось меньше <b>{remaining}</b> постов до бамп-лимита.",
            "⚠️ Внимание, аноны! Тред «<b>{title}</b>» почти забит. Осталось <b>{remaining}</b> мест.",
            "⚠️ Тред «<b>{title}</b>» подходит к концу, осталось всего <b>{remaining}</b> сообщений. Успейте высказаться!",
            "⚠️ Тред «<b>{title}</b>» почти заполнен! Осталось {remaining} постов.",
            "📉 Скоро бамп-лимит в треде «<b>{title}</b>» ({remaining} мест).",
            "🛑 Тред «<b>{title}</b>» скоро закроется (осталось {remaining})."
        ],
        
        # --- Жизненный цикл треда ---
        'thread_archived': [
            "🔒 Все, приехали. Тред достиг лимита в {limit} постов и сдох. R.I.P.", "🔒 Этот тред забит под завязку ({limit} постов) и заархивирован. Ищите новый.",
            "🔒 Тред утонул в сообщениях ({limit} постов) и ушел в архив. F.", "🔒 Лимит в {limit} постов достигнут. Тред закрыт и отправлен на полку.",
            "🔒 Тред переполнен ({limit} постов) и больше неактивен. Покойся с миром.", "🔒 Бамп-лимит. Тред «{title}» заархивирован.",
            "🔒 {limit} постов. Этот тред официально мертв. Архив.", "🔒 Тред исчерпал себя. {limit} сообщений. Архив.",
            "🔒 Конец истории. Тред забит и убран в архив.", "🔒 Этот тред полон. {limit} постов. Он закрыт.",
            "🔒 Тред достиг лимита ({limit} постов) и заархивирован.", "🛑 Бамп-лимит! Тред «{title}» закрыт и отправлен в архив.",
            "🧊 Тред «{title}» замерз. Новые ответы не принимаются."
        ],
        'oldest_thread_removed': [
            "🗑 На доске тесно, поэтому самый старый тред «{title}» был смыт в унитаз. Место для нового дерьма освобождено.",
            "🗑 Чтобы ты мог создать свой высер, пришлось утопить самый несвежий тред «{title}»", "🗑 Старый тред «{title}» стух и был удален, чтобы освободить место. Такие дела.",
            "🗑 Помашите ручкой треду «{title}». Он был самым старым и уступил место новому.", "🗑 Для нового треда пришлось пожертвовать старым. «{title}» отправляется в небытие.",
            "🗑 Тред «{title}» был слишком стар для этого дерьма. Он удален.", "🗑 Чтобы освободить место, самый неактивный тред «{title}» был уничтожен.",
            "🗑 «{title}»? Забудьте. Этот тред удален ради нового.", "🗑 Произошла чистка. Самый древний тред «{title}» удален.",
            "🗑 Жизненный цикл завершен. Тред «{title}» удален, чтобы освободить место.",
            "🗑 Старый тред «{title}» был удален, чтобы освободить место.", "💀 Тред «{title}» умер от старости и был удален.",
            "♻️ Ротация тредов: «{title}» удален."
        ],
        
        # --- История ---
        'show_history_button': [
            "📜 Дайте всю историю", "📜 Показать простыню", "📜 Всю историю, быстро!", "📜 Вывалить все посты", "📜 Посмотреть с самого начала",
            "📜 Загрузить весь тред", "📜 Хочу видеть всё", "📜 Вся летопись", "📜 Показать весь срач", "📜 Полная история",
            "📜 Отмотать в начало", "📜 Покажи, с чего все началось", "📜 Всю подноготную", "📜 Загрузить архив", "📜 Нужна вся история",
            "📜 Показать все сообщения", "📜 Полный лог", "📜 История сообщений", "📜 Весь тред", "📜 Экскурс в историю",
        ],
        'history_cooldown': [
            "⏳ Историю можно запрашивать раз в {minutes} минут. Не спамь.", "⏳ Часто дрочишь на историю. Подожди {minutes} минут.",
            "⏳ Не так часто. Кулдаун на историю - {minutes} минут.", "⏳ Тормози, история никуда не денется. Жди {minutes} минут.",
            "⏳ Заебал со своей историей. Откат {minutes} минут.", "⏳ Полегче, архивариус. Пауза {minutes} минут.",
            "⏳ Любовь к истории похвальна, но есть кулдаун. {minutes} минут.", "⏳ Ты уже запрашивал историю. Подожди {minutes} минут.",
            "⏳ Хватит долбить кнопку истории. КД {minutes} минут.", "⏳ История - вещь неспешная. Кулдаун {minutes} минут.",
            "⏳ Историю можно запрашивать раз в {minutes} мин.", "⏳ Не спамь запросами истории. Жди {minutes} минут.",
            "⏳ Архив треда собирается. Подожди {minutes} мин."
        ],
        
        # --- Модерация (ДЛЯ ОПА - ПОЛНОСТЬЮ АНОНИМНО) ---
        'op_mute_success': [
            "🔇 Заткнул этого хуесоса на {duration} минут.", "🔇 Выдал кляп этому долбоебу на {duration} минут.", "🔇 Этот пидорас теперь молчит. На {duration} минут.",
            "🔇 Все, этот посидит в тишине {duration} минут.", "🔇 Минус один. Замутил его на {duration} минут.", "🔇 Этот допизделся. Мьют на {duration} минут.",
            "🔇 Завалил ебало одному. Отдохнет {duration} минут.", "🔇 Отправил этого в режим 'только чтение' на {duration} минут.", "🔇 Готово. Этот больше не кукарекает. {duration} минут тишины.",
            "🔇 Успешно заткнул. Срок: {duration} минут.", "🔇 Этот персонаж временно обеззвучен на {duration} минут.", "🔇 Забанил этого клоуна на {duration} минут. В своем треде, конечно.",
            "🔇 Этот больше не скажет ни слова. {duration} минут молчания.", "🔇 Приглушил одного. На {duration} минут.", "🔇 Успех. Этот пользователь замучен на {duration} минут.",
            "🔇 Этот парень доигрался. Мьют на {duration} минут.", "🔇 Заткнул фонтан красноречия на {duration} минут.", "🔇 Этот долбаеб отправлен в мут на {duration} минут.",
            "🔇 Миссия выполнена. Цель замолчала на {duration} минут.", "🔇 Право голоса отозвано на {duration} минут.",
            "Пользователь замучен в этом треде.", "ОП воспользовался банхаммером. Юзер молчит.",
            "Правосудие ОПа свершилось. Мут выдан."
        ],
        'op_unmute_success': [
            "🔊 Ладно, пусть говорит. Размутил.", "🔊 Снял кляп с этого.", "🔊 Помиловал. Пусть снова пишет.", "🔊 Разбанил этого бедолагу.",
            "🔊 Пусть живет. Снял мьют.", "🔊 Окей, он снова в игре.", "🔊 Разрешил ему снова открывать рот.", "🔊 Мьют снят. Можешь дальше его травить.",
            "🔊 Ладно, амнистия.", "🔊 Вернул этому право голоса.", "🔊 Размучен. Пусть скажет спасибо.", "🔊 Снял бан. Пусть теперь думает, что пишет.",
            "🔊 Окей, помилован. На этот раз.", "🔊 Выпустил из клетки. Пусть пишет.", "🔊 Разрешаю этому снова говорить.", "🔊 Он снова может писать. Твоя ответственность.",
            "🔊 Ладно, фиг с ним. Размучен.", "🔊 Амнистирован.", "🔊 Снял мьют. Продолжайте.", "🔊 Этот снова с вами. Размутил.",
            "Пользователь размучен.", "ОП сменил гнев на милость.",
            "Голос возвращен."
        ],

        # --- Модерация (ДЛЯ АДМИНОВ - С ID) ---
        'shadowmute_threads_success': [
            "👤 Пользователь {user_id} теперь пишет в пустоту во всех тредах. На {duration} минут.",
            "👤 Выдал {user_id} билет в театр теней на {duration} минут. Он будет писать, но его никто не увидит.",
            "👤 {user_id} отправлен в Шэдоу-бан во всех тредах на {duration} минут.", "👤 Пользователь {user_id} теперь говорит со стеной во всех тредах. Срок: {duration} минут.",
            "👤 Активирован режим 'игнор' для {user_id} во всех тредах на {duration} минут.", "👤 {user_id} помещен в персональный вакуум. Будет писать, но его сообщения не дойдут. {duration} минут.",
            "👻 Пользователь {user_id} получил теневой бан во всех тредах на {duration} мин.", "👻 Тихий режим для {user_id} активирован в тредах ({duration} мин)."
        ],
        'main_chat_activity_notification': [
            "📢 Пока ты сидишь в треде, на основной доске появилось <b>{count}</b> новых постов. Может, стоит проверить?",
            "📢 Не пропусти движуху! На доске уже <b>{count}</b> новых сообщений.",
            "📢 В общем чате накопилось <b>{count}</b> постов. Возвращайся через /leave, если интересно.",
        ],
        'thread_activity_notification': [
            "🔥 В треде «<b>{title}</b>» начался сущий ад! Уже <b>{count}</b> новых постов. Залетай!",
            "🔥 Аноны устроили срач в треде «<b>{title}</b>»! Там уже <b>{count}</b> новых сообщений.",
            "🔥 Тред «<b>{title}</b>» разгоняется! <b>{count}</b> новых постов. Не пропусти самое интересное.",
            "🔥 В треде «{title}» суета! ({count} новых постов)", "📈 Активность в треде «{title}» повысилась! (+{count})",
            "⚡ Тред «{title}» ожил, залетайте! (+{count} постов)", "🗣️ В треде «{title}» идет бурная дискуссия."
        ],

        # --- Кнопки ---
        'prev_page_button': ["⬅️ Сюда", "⬅️ Назад", "⬅️ Предыдущая", "⬅️ Обратно"],
        'next_page_button': ["Туда ➡️", "Дальше ➡️", "Следующая ➡️", "Вперед ➡️"],
    },
    'en': {
        # --- Thread Creation ---
        'create_usage': [
            "🚫 Bullshit. Use: <code>/create &lt;awesome_thread_title&gt;</code>", "🚫 Nope, not like that. Format: <code>/create &lt;thread_name&gt;</code>",
            "🚫 Are you dumb? You need to <code>/create &lt;title&gt;</code>.", "🚫 Syntax error in your brain. Example: <code>/create Anime flame war</code>",
            "🚫 All thumbs? Command: <code>/create &lt;title_text&gt;</code>", "🚫 Wrong. Use: <code>/create &lt;what_your_shitpost_is_about&gt;</code>",
            "🚫 No. No. No. <code>/create &lt;title&gt;</code>. Remember it.", "🚫 What's the format? <code>/create &lt;name&gt;</code>. Got it?",
            "🚫 You missed the main part - the title. <code>/create TITLE</code>", "🚫 Just type <code>/create</code> and then the thread name. Is it that hard?",
            "🚫 After /create command must be a title of your thread, you moron.", "🚫 Where is the title, I ask? <code>/create NAME</code>",
            "🚫 You're trying to create a thread with no name. Genius. But no.", "🚫 Command, then space, then title. Burn it into your memory.",
            "🚫 /create, then the title. Not the other way around. Don't be an ass.", "🚫 Hello, McFly! <code>/create &lt;title&gt;</code>. For the slow ones.",
            "🚫 You forgot the point. <code>/create &lt;THE_POINT&gt;</code>.", "🚫 Turn on your brain. <code>/create &lt;thread_title&gt;</code>.",
            "🚫 I don't understand what you want. Try <code>/create &lt;a_clear_title&gt;</code>.", "🚫 First /create, then the title. Is it that difficult?",
        ],
        'create_success': [
            "✅ Alright, thread \"<b>{title}</b>\" just dropped. Get in and discuss.", "✅ Your shitpost \"<b>{title}</b>\" is now live. Don't fuck it up.",
            "✅ Thread \"<b>{title}</b>\" created successfully. Waiting for the experts.", "✅ We have a breach! Thread \"<b>{title}</b>\" has appeared on the board.",
            "✅ Thread \"<b>{title}</b>\" is a go. Let the flaming begin.", "✅ Your topic \"<b>{title}</b>\" has been created. You're welcome.",
            "✅ Let's start a new flame war: \"<b>{title}</b>\". Join in.", "✅ New thread \"<b>{title}</b>\" is here. Get in.",
            "✅ Done. Thread \"<b>{title}</b>\" is waiting for your messages.", "✅ Let the games begin. Thread \"<b>{title}</b>\" is on air.",
        ],
        'create_success_with_purge': [
            "✅ Your thread '<b>{title}</b>' is live. To make room, the stalest thread '<b>{old_title}</b>' was flushed down the toilet.",
            "✅ Created '<b>{title}</b>'. But the board ain't made of rubber, so the most stalled thread '<b>{old_title}</b>' got the boot.",
            "✅ Space for your shitpost '<b>{title}</b>' was cleared at the cost of the most inactive thread, '<b>{old_title}</b>'. F.",
            "✅ Congrats, '<b>{title}</b>' is on air. Had to put down the deadest thread '<b>{old_title}</b>' to make it happen, though. No one was bumping it anyway.",
            "✅ Your thread '<b>{title}</b>' has replaced the dullest and most forgotten thread '<b>{old_title}</b>'. The circle of life... and shitposts.",
            "✅ To squeeze in your '<b>{title}</b>', we had to toss out the dustiest junk from the attic - goodbye, '<b>{old_title}</b>'.",
            "✅ We have '<b>{title}</b>'! But due to our 'one in, one out' policy, the least active thread '<b>{old_title}</b>' has permanently left the chat.",
            "✅ Rolled in your '<b>{title}</b>', but it came at a price. The sacrifice was the most unpopular thread, '<b>{old_title}</b>'.",
            "✅ Your thread '<b>{title}</b>' has been created. Meanwhile, the most boring thread '<b>{old_title}</b>' has been recycled.",
            "✅ '<b>{title}</b>' is here. P.S. The deadest thread '<b>{old_title}</b>' was sacrificed to the content gods.",
            "✅ '<b>{title}</b>' was created. At the same time the most forgotten thread '<b>{old_title}</b>' was put to the sword.",
            "✅ Thread '<b>{title}</b>' has taken the place of the deceased thread '<b>{old_title}</b>', which no one was interested in anymore.",
            "✅ Congratulations on creating '<b>{title}</b>'. The most abandoned thread '<b>{old_title}</b>' has been deleted to free up space.",
            "✅ '<b>{title}</b>' bursts onto the board, pushing out the most static thread '<b>{old_title}</b>' with its arrival.",
            "✅ Had to do a little cleaning. Thread '<b>{old_title}</b>' was deleted so your '<b>{title}</b>' could live. Enjoy.",
        ],
        'create_invalid_input': [
            "🚫 Hey, I'm waiting for text, not... whatever this is. Give me the OP.",
            "🚫 Are you kidding me? I need text for the thread, not stickers.",
            "🚫 Nope, that won't work. Send me the text that will be the first post.",
            "🚫 Text is expected. Only text. Letters, words, sentences. Got it?",
            "🚫 Very funny, but I'm waiting for the text for the opening post.",
            "🚫 A thread from a picture? Original, but no. Let's have some text.",
            "🚫 Hello? I need text! What are you sending me?",
            "🚫 Send me a proper text post, not this.",
            "🚫 Where's the text? I can't read minds or stickers.",
            "🚫 The opening post must be text. Try again.",
        ],
        'create_prompt_op_post': [
            "Write the text for the Opening Post (OP) of your thread.",
            "What is your thread about? Send the OP text.",
            "Waiting for text to create a new thread. Surprise me.",
            "Send the content of the first post to start a discussion."
        ],
        'create_prompt_op_post_edit': [
            "Okay, send the new text for the OP.",
            "Enter the corrected text for the header/post."
        ],
        'create_confirmation': [
            "Thread ready. Publish?",
            "Is this correct? Create thread with this text?",
            "Confirm thread creation."
        ],
        'create_cancelled': [
            "Thread creation cancelled. Come back when you're ready.",
            "Cancelled. Thread not created.",
            "Operation aborted. You can continue shitposting on main."
        ],
        'create_cooldown': [
            "⏳ Hold your horses, cowboy. New threads once every {minutes} minutes. Wait {remaining}.", "⏳ Cool it, writer. Cooldown is {minutes} minutes. Remaining: {remaining}.",
            "⏳ Stop spamming threads, you fuck. Wait {remaining} before trying again.", "⏳ Slow down there. You can create threads once every {minutes} minutes. Left: {remaining}.",
            "⏳ Not so fast, hotshot. Cooldown {minutes} minutes. Wait {remaining}.", "⏳ You're not a machine gun, and I'm not a thread warehouse. Rest for {remaining}.",
            "⏳ You're shitting too much. Limit: one thread per {minutes} minutes. Remaining: {remaining}.", "⏳ The server isn't made of iron. Pause for {minutes} minutes. You have to wait {remaining}.",
            "⏳ Stop. Just stop. Wait for {remaining}.", "⏳ Calm down. Next thread in {remaining}.",
            "⏳ Your thread production line is on hold. CD {minutes} min. Remaining: {remaining}.", "⏳ Are you a genius? No, you're on cooldown. Wait {remaining}.",
            "⏳ You think you're the only smart one here? Cooldown. Wait {remaining}.", "⏳ Stop spamming. Pause for {minutes} minutes. You have {remaining} left.",
            "⏳ Take a {minutes}-minute break. Don't create threads so often. Left: {remaining}.", "⏳ The thread factory is closed for {minutes} minutes. Wait {remaining}.",
            "⏳ Your stream of consciousness is too turbulent. Slow down for {remaining}.", "⏳ You are not a factory. Cooldown {minutes} minutes. Remaining: {remaining}.",
            "⏳ Take a rest. Seriously. Next thread in {remaining}.", "⏳ You've created a thread recently. Wait {remaining}.",
            "⏳ Not so fast! You can create a new thread in {minutes} min.", "⏳ Creative block? Wait {minutes} minutes before creating a new thread.",
            "⏳ Cooldown on threads: {minutes} min."
        ],
        'new_thread_public_notification': [
            "🌱 A new thread has sprouted on the board: \"<b>{title}</b>\". Join while it's fresh!",
            "🚨 ALERT! A new thread has been detected: \"<b>{title}</b>\". All anons are welcome.",
            "✨ The board smells of fresh content. A thread called \"<b>{title}</b>\" was just created.",
            "📢 Someone just created a new thread: \"<b>{title}</b>\". Hit the button below to jump in.",
            "💬 A new discussion room has opened on the board: \"<b>{title}</b>\".",
            "📜 A new thread has been started: \"<b>{title}</b>\". All are invited to participate.",
            "🔥 A new hub for discussion! Jump into the thread \"<b>{title}</b>\".",
            "🔔 A new thread has appeared on the board: \"<b>{title}</b>\". We await your opinion.",
            "💡 There's a new topic to talk about: \"<b>{title}</b>\". Join the conversation!",
            "🆕 Attention! New thread: \"<b>{title}</b>\". Get in here.",
            "🌱 <b>New thread:</b> «{title}»", "🆕 <b>Thread created:</b> «{title}»",
            "🔥 <b>Fresh thread:</b> «{title}»", "✨ <b>New discussion:</b> «{title}»"
        ],
        'thread_activity_notification': [
            "🔥 Busy thread «{title}»! ({count} new posts)", "📈 Activity in «{title}» spiked! (+{count})",
            "⚡ Thread «{title}» is alive, get in! (+{count} posts)", "🗣️ Heated discussion in «{title}»."
        ],
        'enter_thread_prompt': [
            "You are in \"<b>{title}</b>\".\n\n📝 Post your bullshit here.\n🚪 To get out - /leave.", "Entered \"<b>{title}</b>\".\n\n📝 Messages now go here.\n🚪 /leave to bail.", "Okay, you're in \"<b>{title}</b>\".\n\n📝 Post here, exit via /leave.", "Welcome to the shitshow \"<b>{title}</b>\".\n\n🚪 /leave to escape.", "You are now a participant in thread \"<b>{title}</b>\".\n\n📝 Post your crap right here.\n🚪 Exit - /leave.",
            "You entered thread: <b>{title}</b>", "Welcome to thread: <b>{title}</b>", "Moved to thread: <b>{title}</b>. Discuss."
        ],
        'enter_thread_success': [
            "Back in \"<b>{title}</b>\".", "You've returned to \"<b>{title}</b>\".", "Here again. Thread \"<b>{title}</b>\".", "Hello again in thread \"<b>{title}</b>\".", "Returning to \"<b>{title}</b>\".", "You're in thread \"<b>{title}</b>\" again.", "Switched back to \"<b>{title}</b>\".", "Comeback to \"<b>{title}</b>\".", "Okay, you are in \"<b>{title}</b>\".", "You are in place. Thread \"<b>{title}</b>\".",
            "You returned to thread: <b>{title}</b>", "Welcome back to: <b>{title}</b>", "Continuing discussion in: <b>{title}</b>"
        ],
        'leave_thread_success': [
            "Bailed from the thread. You're back in the main chat.", "Returned to the main dumpster. The thread is behind you.", "Okay, you've left. Back to the main board.", "Exited the thread. You're in the main channel.", "Escaped. You are back in the main chat.", "You've left the thread. Back to the roots.", "Returning to home base. You are no longer in the thread.", "The thread is behind you. You are in the main chat.", "Okay, you've surfaced. You are on the main board.", "Exited. Back in the stream of consciousness.",
            "You left the thread for the main board.", "Back to zero. You left the thread.", "Exited to main.", "Thread left. You are in the main stream again."
        ],
        'location_switch_cooldown': [
            "⏳ Not so fast, asshole.", "⏳ Easy there. Don't click so often.", "⏳ Chill. Give the server a break.", "⏳ Calm down, Flash. You can't switch that fast.", "⏳ Too fast. Try again in a couple of seconds.", "⏳ Anti-spam protection. Wait a bit.", "⏳ Don't twitch so much. Pause.", "⏳ You're annoying. Wait.", "⏳ Stop jumping back and forth. Cooldown.", "⏳ Overheating! Cool down.",
            "⏳ Switching too fast. Wait a bit.", "⏳ Don't jump between threads so fast. Chill.", "⏳ Wait a few seconds before entering/exiting."
        ],
        'thread_not_found': [
            "🚫 The thread is dead or never existed.", "🚫 This thread is rotten and has been archived.", "🚫 No thread for you. Not found.", "🚫 This thread does not exist. Sorry.", "🚫 Can't find this thread. Maybe it's deleted.", "🚫 The thread is lost. Or you are.", "🚫 404 Thread Not Found.", "🚫 This thread is over. Finita la commedia.", "🚫 Looks like the thread went to the great beyond.", "🚫 No such thread. Never was.",
            "Thread not found or deleted.", "This thread no longer exists.", "404: Thread not found.", "Looks like this thread drowned."
        ],
        'thread_reaching_bump_limit': [
            "⚠️ Thread \"<b>{title}</b>\" is reaching its bump limit! Less than <b>{remaining}</b> posts left.",
            "⚠️ Attention, anons! Thread \"<b>{title}</b>\" is almost full. Only <b>{remaining}</b> slots left.",
            "⚠️ The thread \"<b>{title}</b>\" is nearing its end, only <b>{remaining}</b> messages left. Say your piece now!",
            "⚠️ Thread «{title}» is almost full! {remaining} posts left.", "📉 Bump limit soon in «{title}» ({remaining} slots).", "🛑 Thread «{title}» closing soon ({remaining} left)."
        ],
        'threads_list_header': ["📋 <b>Current shitposts on this board:</b>", "📋 <b>Active threads, get in:</b>", "📋 <b>List of hot discussions:</b>", "📋 <b>Here's what they're chewing on now:</b>", "📋 <b>The flame war zone is open:</b>", "📋 <b>Thread board:</b>", "📋 <b>Live threads at the moment:</b>", "📋 <b>What's up on the board:</b>", "📋 <b>Current threads:</b>", "📋 <b>Look where you can jump in:</b>"],
        'threads_list_empty': [
            "This board is as empty as your head. Create the first thread.", "No threads here yet. Be the first, don't be a pussy.", "Not a single thread. At all. This board is dead.", "Zilch. Create a thread, become the OP.", "Emptiness. Silence. Break it, create a thread.", "Your thread could be here, but it's not.", "Nobody is discussing anything. Boring. Create a thread.", "Like a tomb. Not a single thread.", "Start the action, create the first thread.", "Zero threads. Absolute zero.",
            "No active threads on this board yet.", "Thread list is empty. Create the first one!", "Silence... No threads."
        ],
        'thread_list_item': "{index}. <b>{title}</b> | Posts: {posts_count} | Activity: {last_activity}",
        'thread_archived': [
            "🔒 That's all, folks. The thread hit the {limit} post limit and died. R.I.P.", "🔒 This thread is full ({limit} posts) and has been archived. Find a new one.", "🔒 The thread drowned in messages ({limit} posts) and went to the archive. F.", "🔒 The limit of {limit} posts has been reached. The thread is closed and shelved.", "🔒 The thread is full ({limit} posts) and no longer active. Rest in peace.",
            "🔒 Thread reached limit ({limit} posts) and is archived.", "🛑 Bump limit! Thread «{title}» closed and archived.", "🧊 Thread «{title}» frozen. No new replies accepted."
        ],
        'oldest_thread_removed': [
            "🗑 It's crowded here, so the oldest thread \"{title}\" was flushed down the toilet. Space for new shit has been cleared.", "🗑 To let you create your masterpiece, we had to sink the stalest thread \"{title}\".", "🗑 The old thread \"{title}\" went stale and was deleted to make room. That's life.", "🗑 Wave goodbye to thread \"{title}\". It was the oldest and made way for a new one.", "🗑 A sacrifice was made for a new thread. \"{title}\" is gone.",
            "🗑 Old thread «{title}» was deleted to free up space.", "💀 Thread «{title}» died of old age and was deleted.", "♻️ Thread rotation: «{title}» deleted."
        ],
        'show_history_button': ["📜 Gimme the whole story", "📜 Show the wall of text", "📜 Full history, now!", "📜 Dump all posts", "📜 Show me from the beginning", "📜 Load the whole thread", "📜 I want to see everything", "📜 The whole chronicle", "📜 Show the whole flame war", "📜 Full history"],
        'history_cooldown': [
            "⏳ You can request history once every {minutes} minutes. Don't spam.", "⏳ You're jerking off to history too much. Wait for {minutes} minutes.", "⏳ Not so often. History cooldown is {minutes} minutes.", "⏳ Slow down, the history isn't going anywhere. Wait {minutes} minutes.", "⏳ You're fucking annoying with your history requests. Cooldown {minutes} minutes.", "⏳ Easy, archivist. Pause for {minutes} minutes.",
            "⏳ You can request history once every {minutes} min.", "⏳ Don't spam history requests. Wait {minutes} minutes.", "⏳ Thread archive is assembling. Wait {minutes} min."
        ],
        'op_mute_success': [
            "🔇 Muted this asshole for {duration} minutes.", "🔇 Gagged this dumbass for {duration} minutes.", "🔇 This fucker is silent now. For {duration} minutes.", "🔇 That's it, this one will sit quietly for {duration} minutes.", "🔇 Minus one. Muted him for {duration} minutes.", "🔇 This one talked too much. Mute for {duration} minutes.", "🔇 Shut this one's pie hole. He'll rest for {duration} minutes.", "🔇 Sent this one to 'read-only' mode for {duration} minutes.", "🔇 Done. This one won't be chirping anymore. {duration} minutes of silence.", "🔇 Successfully gagged. Term: {duration} minutes.",
            "User muted in this thread.", "OP used the banhammer. User silenced.", "OP's justice served. Mute applied."
        ],
        'op_unmute_success': [
            "🔊 Alright, let him speak. Unmuted.", "🔊 Took the gag off this one.", "🔊 Pardoned. Let him write again.", "🔊 Unbanned this poor bastard.", "🔊 Let him live. Mute removed.", "🔊 Okay, he's back in the game.", "🔊 Allowed him to open his mouth again.", "🔊 Mute removed. You can continue to troll him.", "🔊 Alright, amnesty.", "🔊 Gave this one his voice back.",
            "User unmuted.", "OP showed mercy.", "Voice returned."
        ],
        'shadowmute_threads_success': [
            "👤 User {user_id} is now posting into the void in all threads. For {duration} minutes.", "👤 Gave {user_id} a ticket to the shadow realm for {duration} minutes. They can post, but no one will see.", "👤 {user_id} has been shadowbanned in all threads for {duration} minutes.", "👤 User {user_id} is now talking to a wall in all threads. Term: {duration} minutes.", "👤 'Ignore' mode activated for {user_id} in all threads for {duration} minutes.",
            "👻 User {user_id} shadowbanned in all threads for {duration} min.", "👻 Silent mode for {user_id} activated in threads ({duration} min)."
        ],
        'main_chat_activity_notification': [
            "📢 While you're in the thread, <b>{count}</b> new posts appeared on the main board. Maybe check it out?",
            "📢 Don't miss the action! Board has <b>{count}</b> new messages.",
            "📢 <b>{count}</b> posts accumulated in main chat. Return via /leave if interested."
        ],
        'prev_page_button': ["⬅️ This way", "⬅️ Back", "⬅️ Previous"],
        'next_page_button': ["That way ➡️", "Next ➡️", "Forward ➡️"],
    },
    'jp': {
        'create_prompt_op_post': [
            "スレッドの最初の投稿（OP）のテキストを書いてください。",
            "スレッドのテーマは何ですか？OPのテキストを送信してください。",
            "新しいスレを立てるためのテキストを待っています。驚かせてください。",
            "議論を始めるために最初のレスの内容を送信してください。"
        ],
        'create_prompt_op_post_edit': [
            "分かりました。新しいOP本文を送信してください。",
            "修正したタイトル/本文を入力してください。"
        ],
        'create_confirmation': [
            "スレッド作成の準備ができました。公開しますか？",
            "これで正しいですか？このテキストでスレを立てますか？",
            "スレッド作成を確認してください。"
        ],
        'create_cancelled': [
            "スレッド作成をキャンセルしました。準備ができたら戻ってきてください。",
            "キャンセル。スレは作成されませんでした。",
            "操作中断。メイン板でのクソ投稿を続けてください。"
        ],
        'create_cooldown': [
            "⏳ 早すぎます！次のスレッドは {minutes} 分後に作成できます。",
            "⏳ スランプですか？ {minutes} 分待ってから新スレを立ててください。",
            "⏳ 落ち着け。スレ立てクールダウン: {minutes} 分。"
        ],
        'create_invalid_input': [
            "テキストに見えません。テキストまたはキャプション付きの画像を送信してください。",
            "OP用のテキストが必要です。もう一度試してください。",
            "理解できません。テキストを送ってください。"
        ],
        'new_thread_public_notification': [
            "🌱 <b>新着スレッド:</b> «{title}»",
            "🆕 <b>スレ立て:</b> «{title}»",
            "🔥 <b>新鮮なスレ:</b> «{title}»",
            "✨ <b>新しい議論:</b> «{title}»"
        ],
        'thread_activity_notification': [
            "🔥 スレッド «{title}» が盛り上がっています！ ({count} 新着レス)",
            "📈 «{title}» のアクティビティが急上昇！ (+{count})",
            "⚡ スレ «{title}» は生きてます、入れ！ (+{count} レス)",
            "🗣️ «{title}» で激しい議論が行われています。"
        ],
        'enter_thread_prompt': [
            "スレッドに入室しました: <b>{title}</b>",
            "ようこそ: <b>{title}</b>",
            "<b>{title}</b> に移動しました。議論しましょう。"
        ],
        'enter_thread_success': [
            "スレッドに戻りました: <b>{title}</b>",
            "お帰りなさい: <b>{title}</b>",
            "<b>{title}</b> で議論を続けます"
        ],
        'leave_thread_success': [
            "スレッドを出てメイン板に戻りました。",
            "ゼロに戻る。スレッドを去りました。",
            "メインに退出しました。",
            "スレッドを離脱。再びメインストリームにいます。"
        ],
        'thread_not_found': [
            "スレッドが見つからないか、削除されました。",
            "このスレッドはもう存在しません（または存在しませんでした）。",
            "404: スレッドが見つかりません。",
            "このスレッドは深淵に沈んだようです。"
        ],
        'location_switch_cooldown': [
            "⏳ 切り替えが速すぎます。少し待ってください。",
            "⏳ そんなに速くスレを飛び回るな。落ち着け。",
            "⏳ 入退室の前に数秒待ってください。"
        ],
        'history_cooldown': [
            "⏳ 履歴は {minutes} 分に1回リクエストできます。",
            "⏳ 履歴リクエストを連打しないでください。 {minutes} 分待ってください。",
            "⏳ スレッドアーカイブを収集中です。 {minutes} 分お待ちください。"
        ],
        'thread_archived': [
            "🔒 スレッドが制限（{limit} レス）に達したためアーカイブされました。",
            "🛑 バンプ制限！スレ «{title}» は閉じられアーカイブされました。",
            "🧊 スレ «{title}» は凍結されました。新しい返信は受け付けません。"
        ],
        'oldest_thread_removed': [
            "🗑 古いスレッド «{title}» はスペース確保のために削除されました。",
            "💀 スレ «{title}» は老衰で死に、削除されました。",
            "♻️ スレッドローテーション: «{title}» 削除。"
        ],
        'op_mute_success': [
            "ユーザーはこのスレッドでミュートされました。",
            "スレ主がBANハンマーを使いました。ユーザーは沈黙しました。",
            "スレ主の正義が執行されました。ミュート適用。"
        ],
        'op_unmute_success': [
            "ユーザーのミュートが解除されました。",
            "スレ主が慈悲を示しました。",
            "声が戻りました。"
        ],
        'thread_reaching_bump_limit': [
            "⚠️ スレ «{title}» はもうすぐ満杯です！残り <b>{remaining}</b> レス。",
            "📉 «{title}» のバンプ制限が近いです（残り <b>{remaining}</b> 枠）。",
            "🛑 スレ «{title}» はもうすぐ閉じます（残り <b>{remaining}</b>）。"
        ],
        'threads_list_empty': [
            "この板にはまだアクティブなスレッドがありません。",
            "スレッドリストは空です。最初の1つを作成してください！",
            "静寂... スレなし。"
        ],
        'shadowmute_threads_success': [
            "👻 ユーザー {user_id} は全スレッドで {duration} 分間シャドウバンされました。",
            "👻 {user_id} のサイレントモードがスレッド内で有効化されました（{duration} 分）。"
        ],
        'threads_list_header': [
            "📋 <b>現在のクソスレ一覧:</b>", "📋 <b>アクティブなスレッド、入れ:</b>", "📋 <b>熱い議論のリスト:</b>",
            "📋 <b>今話題のネタ:</b>", "📋 <b>レスバトルゾーン開放中:</b>", "📋 <b>スレッド一覧:</b>",
            "📋 <b>現在進行中のスレ:</b>", "📋 <b>板の状況:</b>", "📋 <b>カレントスレッド:</b>",
            "📋 <b>飛び込める場所はここだ:</b>"
        ],
        'thread_list_item': "{index}. <b>{title}</b> | レス数: {posts_count} | 最終: {last_activity}",
        'main_chat_activity_notification': [
            "📢 スレッドにいる間に、メインボードに <b>{count}</b> 件の新しい投稿がありました。",
            "📢 動きを見逃すな！ボードにはすでに <b>{count}</b> 件の新しいメッセージがあります。",
            "📢 一般チャットに <b>{count}</b> 件の投稿が蓄積されました。興味があれば /leave で戻ってください。"
        ],
        'prev_page_button': ["⬅️ 前へ", "⬅️ 戻る"],
        'next_page_button': ["次へ ➡️", "進む ➡️"]
    }
}