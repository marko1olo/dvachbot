# -*- coding: utf-8 -*-
"""
common/work_engine.py — Comprehensive Hybrid Work & Gig Economy Engine for ТГАЧ
Combines the authentic 9 imageboard career tiers with 100+ authentic chan phrases,
RPG wardrobe gear buffs, set bonuses, milestone achievements, and random item/lootbox drops.
"""

import time
import random
import re
from typing import Dict, Any, Tuple, Optional

# -----------------------------------------------------------------------------
# 9 Career Tiers (Authentic Dvach Lore & High-Stakes Progression)
# -----------------------------------------------------------------------------

WORK_VACANCIES: Dict[str, Dict[str, Any]] = {
    "bottles": {
        "title": "🍾 Сбор стеклотары / Помойка",
        "desc": "Обход мусорных баков у метро, сбор пивных бутылок и алюминиевых банок",
        "tier": "Уровень 1 • Бомж",
        "required_shifts": 0,
        "reward_range": (15, 45),
        "cooldown_sec": 180,  # 3 min
        "risk_pct": 0.0,
        "penalty": 0,
        "item_drop": "trash_lootbox",
        "item_drop_chance": 0.08,
        "phrases": [
            "Нашел в урне у метро три чистые бутылки из-под 'Балтики 9': получка <code>+{reward} ₪</code>!",
            "Успешно отжал у голубей пакет с алюминиевыми банками: профит <code>+{reward} ₪</code>!",
            "Сдал пункт приёма 12 бутылок из-под Жигулёвского: скупщик отсыпал <code>+{reward} ₪</code>!",
            "Нашел у помойки рабочий удлинитель и сдал на медь: залутал <code>+{reward} ₪</code>!",
            "Подобрал за гаражами недопитый портвейн и две целые бутылки: профит <code>+{reward} ₪</code>!",
            "Местный дворник сжалился и отдал мешок с банками без драки: заработок <code>+{reward} ₪</code>!",
            "Нашел в контейнере выкинутый советский утюг с медным проводом: выручка <code>+{reward} ₪</code>!",
            "Залез в бак у элитного дома и залутал 5 бутылок из-под дорогого коньяка: <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [],
        "jackpot_phrases": [
            "💎 <b>ЗОЛОТАЯ ЖИЛА!</b> Нашел за супермаркетом забытый ящик дорогого импортного крафта! Куш: <code>+{reward} ₪</code>!"
        ]
    },
    "sweeper": {
        "title": "🧹 Дворник в спальном районе",
        "desc": "Утренняя уборка окурков, борьба с собачниками и расчистка сугробов",
        "tier": "Уровень 2 • Работяга",
        "required_shifts": 3,
        "reward_range": (40, 95),
        "cooldown_sec": 480,  # 8 min
        "risk_pct": 0.08,
        "penalty": 15,
        "item_drop": "janitor_broom",
        "item_drop_chance": 0.06,
        "phrases": [
            "Героически отскрёб жвачки и окурки у третьего подъезда: старшая по дому выдала <code>+{reward} ₪</code>!",
            "Убрал последствия ночной попойки альтушек на детской площадке: ЖКХ перечислило <code>+{reward} ₪</code>!",
            "Расчистил тропинку к алкомаркету в снегопад — благодарные работяги насыпали чаевых: <code>+{reward} ₪</code>!",
            "Помог деду дотащить сломанный телевизор до мусорки: получил щедрые чаевые <code>+{reward} ₪</code>!",
            "Подмёл листву под окнами дома и нашел потерянную сотку: получка <code>+{reward} ₪</code>!",
            "Починил сломанную качель во дворе — мамаши скинулись на чай: <code>+{reward} ₪</code>!",
            "Успешно разогнал закладчиков метлой и навёл порядок у мусорных баков: премия <code>+{reward} ₪</code>!",
            "Покрасил облупленный забор детской площадки яркой краской: ЖЭК начислил <code>+{reward} ₪</code>!",
            "Спас бездомного кота с козырька подъезда — жильцы отсыпали на карман <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🐶 <b>ШТРАФ!</b> Наступил в собачье говно и размазал по подъезду: штраф от начальника ЖЭКа <code>-{penalty} ₪</code>!",
            "Сломал казённую метлу о скамейку: удержание из зарплаты <code>-{penalty} ₪</code>!",
            "Бабка с первого этажа обвинила в краже коврика и написала кляузу: штраф <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ЦАРСКИЙ ПОДГОН!</b> Жилец на Майбахе дал щедрую купюру за расчистку парковочного места! Выручка: <code>+{reward} ₪</code>!"
        ]
    },
    "courier": {
        "title": "🚴 Курьер / Доставка шаурмы",
        "desc": "Гонки на электровелосипеде сквозь пробки и злых собак",
        "tier": "Уровень 3 • Доставщик",
        "required_shifts": 8,
        "reward_range": (80, 160),
        "cooldown_sec": 900,  # 15 min
        "risk_pct": 0.10,
        "penalty": 25,
        "item_drop": "pepperspray",
        "item_drop_chance": 0.06,
        "phrases": [
            "Доставил 10 шавух в общежитие за 12 минут: голодные студенты насыпали чаевых <code>+{reward} ₪</code>!",
            "Успешно увернулся от каршеринга и довез пиццу горячей: сервис начислил <code>+{reward} ₪</code>!",
            "Поднялся на 25 этаж без лифта и спас голодного скуфа: чаевые составили <code>+{reward} ₪</code>!",
            "Успешно сбежал от стаи бродячих собак во дворе и вручил заказ клиенту: получка <code>+{reward} ₪</code>!",
            "Привез суши пьяной компании в сауну — клиенты не пожалели чаевых: <code>+{reward} ₪</code>!",
            "Объехал пробку по встречке и успел за секунду до штрафного таймера: <code>+{reward} ₪</code>!",
            "Вручил праздничный торт имениннице без повреждений крема: щедрый чай <code>+{reward} ₪</code>!",
            "Прорвался через метель на сломанном самокате и закрыл смену в топе курьеров: бонус <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🐕 <b>АТАКА СОБАК!</b> Стая псов прокусила желтый рюкзак и сожрала клиентскую пиццу: компенсация за заказ <code>-{penalty} ₪</code>!",
            "Аккумулятор электробайка взорвался посреди перекрестка: ремонт обошелся в <code>-{penalty} ₪</code>!",
            "Уронил пакет с супом на пороге элитной квартиры: клиент накатал жалобу, штраф <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ОЛИГАРХИЧЕСКИЙ ЗАКАЗ!</b> Доставил лобстеров в Москва-Сити, пьяный криптоинвестор отсыпал котлету! Куш: <code>+{reward} ₪</code>!"
        ]
    },
    "captcha": {
        "title": "⌨️ Ввод капчи на буксах",
        "desc": "Монотонное разгадывание светофоров и пешеходных переходов по 12 часов в сутки",
        "tier": "Уровень 4 • Мамкин Фрилансер",
        "required_shifts": 15,
        "reward_range": (120, 240),
        "cooldown_sec": 1500,  # 25 min
        "risk_pct": 0.12,
        "penalty": 40,
        "item_drop": "tinfoil_hat",
        "item_drop_chance": 0.05,
        "phrases": [
            "Разгадал 2500 картинок со светофорами и автобусами: индийский сервис выплатил <code>+{reward} ₪</code>!",
            "Написал скрипт кликера на автохоткее и ушел пить чай: капнуло <code>+{reward} ₪</code>!",
            "Разгадал аудио-капчу на ломаном немецком: сервис накинул бонус за сложность <code>+{reward} ₪</code>!",
            "Просидел ночь за решением ReCaptcha v3 для спамеров: баланс пополнен на <code>+{reward} ₪</code>!",
            "Обошел защиту Cloudflare вручную для китайских парсеров: заработано <code>+{reward} ₪</code>!",
            "Разгадал 1000 искажённых математических примеров для азиатского бота: получка <code>+{reward} ₪</code>!",
            "Прокликал 500 пазлов с вращением собачек под нужным углом: выплата <code>+{reward} ₪</code>!",
            "Победил hCaptcha на 300 сайтах подряд со скоростью робота: премия за скорость <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "👁️ <b>АНТИФРОД!</b> Нейросеть заподозрила в тебе бота и забанила аккаунт с балансом: сгорело <code>-{penalty} ₪</code>!",
            "Залипание клавиш привело к 50 ошибкам подряд: сервис списал штраф <code>-{penalty} ₪</code>!",
            "Отрубился интернет в момент вывода средств: комиссия за сбой <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>СБОЙ АЛГОРИТМА!</b> Заказчик случайно ошибся нулем в ставке за распознавание базы токенов! Выплата: <code>+{reward} ₪</code>!"
        ]
    },
    "spy": {
        "title": "🕵️ Слив инфы майору / Стукач",
        "desc": "Анонимные доносы на треды, слив IP-адресов вайперов и аналитика для товарища майора",
        "tier": "Уровень 5 • Тайный Осведомитель",
        "required_shifts": 25,
        "reward_range": (200, 420),
        "cooldown_sec": 3600,  # 1 hour
        "risk_pct": 0.15,
        "penalty": 60,
        "item_drop": "gold_safe",
        "item_drop_chance": 0.07,
        "phrases": [
            "Слил майору скриншоты закрытой конфы цпшников: на карту упала секретная премия <code>+{reward} ₪</code>!",
            "Вычислил по логам IP-адрес набегатора и сдал куратору: благодарность в конверте <code>+{reward} ₪</code>!",
            "Задеванонил админа сетки спам-ботов: гонорар за оперативные данные <code>+{reward} ₪</code>!",
            "Сдал товарищу майору схрон запрещенных стикеров: получено вознаграждение <code>+{reward} ₪</code>!",
            "Составил подробный отчет о настроениях в /b/: аналитический отдел выплатил <code>+{reward} ₪</code>!",
            "Зафиксировал деятельность подпольной конфы скамеров и передал флешку куратору: <code>+{reward} ₪</code>!",
            "Нашел скрытую уязвимость в боте конкурентов и доложил в штаб: агентское вознаграждение <code>+{reward} ₪</code>!",
            "Внедрился в закрытый чат трейдеров под видом мамкиного инвестора: аналитический гонорар <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🦹 <b>ДЕАНОН!</b> Местные битарды выложили твои паспортные данные на борду: взятка за удаление треда <code>-{penalty} ₪</code>!",
            "Майор посчитал твой донос ложным и выписал штраф за отвлечение органов: <code>-{penalty} ₪</code>!",
            "Хакеры взломали твой телеграм и перевели деньги фонду помощи шизоидам: потеряно <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>КРУПНАЯ РЫБА!</b> По твоей наводке накрыли подпольную ферму SIM-боксов! Спецпремия: <code>+{reward} ₪</code>!"
        ]
    },
    "factory": {
        "title": "🏭 Завод «Красный Пролетарий»",
        "desc": "12-часовая смена у токарного станка под шансон и гул компрессоров",
        "tier": "Уровень 6 • Заводчанин",
        "required_shifts": 40,
        "reward_range": (320, 650),
        "cooldown_sec": 7200,  # 2 hours
        "risk_pct": 0.15,
        "penalty": 90,
        "item_drop": "knife_gun",
        "item_drop_chance": 0.05,
        "phrases": [
            "Выточил 500 гаек сверх нормы без единого перекура: мастер цеха выдал аванс <code>+{reward} ₪</code>!",
            "Отработал двойную ночную смену за запившего Петровича: двойная ставка составила <code>+{reward} ₪</code>!",
            "Успешно вынес через проходную моток медного кабеля в трусах: сдал в цветмет за <code>+{reward} ₪</code>!",
            "Починил главный гидравлический пресс ударом кувалды: заводской профсоюз премировал на <code>+{reward} ₪</code>!",
            "Сдал план на пятилетку за три дня: директор завода пожал руку и вручил конверт на <code>+{reward} ₪</code>!",
            "Отлил партию чугунных крышек люков без единой раковины: мастер цеха начислил <code>+{reward} ₪</code>!",
            "Отрегулировал шестеренчатый вал на советском станке 1968 года: премия за рацпредложение <code>+{reward} ₪</code>!",
            "Выгрузил вагон угля голыми руками под бодрящий мат бригадира: получка за смену <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🦾 <b>БРАК!</b> Запорол партию титановых болтов для оборонки: лишение премии и вычет <code>-{penalty} ₪</code>!",
            "Попался на проходной с банкой спирта: штраф за нарушение режима <code>-{penalty} ₪</code>!",
            "Уронил деталь на ногу Петровича: оплата лечения коллеги <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>УДАРНИК ТРУДА!</b> Награжден Орденом Стаханова и 13-й зарплатой от гендиректора! Куш: <code>+{reward} ₪</code>!"
        ]
    },
    "it_freelance": {
        "title": "💻 Вебкам / IT-Фриланс",
        "desc": "Пилить кнопки для криптоскамов и верстать лендинги на коленке",
        "tier": "Уровень 7 • Сеньор Помидор",
        "required_shifts": 60,
        "reward_range": (450, 900),
        "cooldown_sec": 10800,  # 3 hours
        "risk_pct": 0.18,
        "penalty": 120,
        "item_drop": "mute_gun",
        "item_drop_chance": 0.05,
        "phrases": [
            "Переписал легаси на Go за одну ночь и задеплоил в прод без тестов: заказчик щедро заплатил <code>+{reward} ₪</code>!",
            "Сверстал сайт-одностраничник для продажи курсов успешного успеха: гонорар составил <code>+{reward} ₪</code>!",
            "Настроил стрим азиатской модели на OnlyFans через OBS: процент с донатов составил <code>+{reward} ₪</code>!",
            "Внедрил ИИ-бота в поддержку банка, бот начал материть клиентов, но KPI выполнен: выплата <code>+{reward} ₪</code>!",
            "Успешно продал заказчику бесплатный шаблон из интернета за 1000$: чистый профит <code>+{reward} ₪</code>!",
            "Пофиксил баг пятилетней давности удалением одной строчки кода: заказчик в восторге отсыпал <code>+{reward} ₪</code>!",
            "Сгенерировал через нейросеть логотип и брендбук за 5 минут: оплата за авторский дизайн <code>+{reward} ₪</code>!",
            "Написал парсер отзывов на маркетплейсах для ушлого селлера: чистый гонорар <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "💥 <b>УРОНИЛ ПРОД!</b> Сделал `DROP DATABASE` на боевом сервере в пятницу вечером: неустойка <code>-{penalty} ₪</code>!",
            "Заказчик оказался школьником и кинул на оплату после сдачи проекта: убыток на хостинг <code>-{penalty} ₪</code>!",
            "Сгорела видеокарта RTX 4090 во время обучения нейросети: экстренный ремонт <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ВЫХОД НА IPO!</b> Твой pet-проект выкупил Яндекс за чемодан шекелей! Профит: <code>+{reward} ₪</code>!"
        ]
    },
    "scam": {
        "title": "🕶️ Теневой Арбитраж & Скам",
        "desc": "Фейковые шопы, развод мамонтов на Авито и крипто-дропы",
        "tier": "Уровень 8 • Темщик",
        "required_shifts": 85,
        "reward_range": (650, 1300),
        "cooldown_sec": 14400,  # 4 hours
        "risk_pct": 0.22,
        "penalty": 200,
        "item_drop": "shield_gun",
        "item_drop_chance": 0.05,
        "phrases": [
            "Успешно продал мамонту виртуальные семена на фейковой бирже: чистый навар <code>+{reward} ₪</code>!",
            "Пампанул шиткоин в закрытом чате хомяков и вовремя вышел на пике: куш <code>+{reward} ₪</code>!",
            "Оформил возврат на маркетплейсе по поддельному чеку: чистая прибыль <code>+{reward} ₪</code>!",
            "Продал китайскую копию AirPods под видом оригинала в метро: профит <code>+{reward} ₪</code>!",
            "Сдал в аренду несуществующую квартиру на Патриарших троим приезжим: залутал <code>+{reward} ₪</code>!",
            "Перехватил дроп редких NFT и перепродал на OpenSea американцам: профит <code>+{reward} ₪</code>!",
            "Запустил фишинговый лендинг с розыгрышем новенького айфона: мамонты занесли <code>+{reward} ₪</code>!",
            "Слил базу 'горячих лидов' криптоэнтузиастов теневому брокеру: куш составил <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "🚔 <b>ОБЛАВА ОБЭП!</b> Следователь вышел на твой след, пришлось откупиться: взятка <code>-{penalty} ₪</code>!",
            "Мамонт оказался оперуполномоченным под прикрытием: еле унёс ноги, потеряв <code>-{penalty} ₪</code>!",
            "Криптобиржа заблокировала аккаунт по 115-ФЗ вместе с депозитом: убыток <code>-{penalty} ₪</code>!",
            "Обманутый перекуп подкараулил у подъезда с битой: оплата больничного <code>-{penalty} ₪</code>!",
            "Скам-смартконтракт взломали хакеры и увели всю кассу: потеряно <code>-{penalty} ₪</code>!",
            "Дроп сбежал со всеми деньгами в Грузию: чистый убыток на <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>СКАМ ВЕКА!</b> Запустил фейковую биржу и залутал миллион долларов у криптофонда! Куш: <code>+{reward} ₪</code>!"
        ]
    },
    "deputy": {
        "title": "🏛️ Помощник депутата / Распил",
        "desc": "Освоение грантов на патриотизм, импортозамещение и укладка плитки",
        "tier": "Уровень 9 • Хозяин Жизни",
        "required_shifts": 120,
        "reward_range": (900, 1800),
        "cooldown_sec": 18000,  # 5 hours
        "risk_pct": 0.25,
        "penalty": 300,
        "item_drop": "megaphone",
        "item_drop_chance": 0.05,
        "phrases": [
            "Успешно освоил грант на создание 'Отечественной ОС на базе Linux': чистый распил <code>+{reward} ₪</code>!",
            "Переложил плитку на центральной площади в третий раз за месяц: подрядчик отстегнул <code>+{reward} ₪</code>!",
            "Выиграл тендер на поставку золотых ершиков в мэрию: откат составил <code>+{reward} ₪</code>!",
            "Запустил патриотический фестиваль с бюджетом в 50 млн (потратил 500 рублей на флажки): профит <code>+{reward} ₪</code>!",
            "Провёл экспертизу школьного питания и закрыл глаза на просрочку: благодарность от поставщика <code>+{reward} ₪</code>!",
            "Пролоббировал запрет самокатов в пользу каршеринга своего племянника: солидный бонус <code>+{reward} ₪</code>!",
            "Одобрил строительство элитного ТЦ на месте исторического сквера: застройщик занёс чемодан на <code>+{reward} ₪</code>!",
            "Списал 10 миллионов на разработку патриотической видеоигры: нарисовали 2 скриншота, остаток в карман: <code>+{reward} ₪</code>!",
            "Продал служебную Камри по остаточной стоимости своей тёще и перепродал на рынке: <code>+{reward} ₪</code>!",
            "Оформил 50 родственников на фиктивные должности консультантов в думу: собрал получки на <code>+{reward} ₪</code>!"
        ],
        "fail_phrases": [
            "⚖️ <b>СЧЁТНАЯ ПАЛАТА!</b> Приехала проверка из Москвы, пришлось экстренно делиться: откат <code>-{penalty} ₪</code>!",
            "ФСБ заинтересовалась поставками песка по цене золота: замятие дела обошлось в <code>-{penalty} ₪</code>!",
            "Конкуренты из другой фракции слили компромат на твои офшоры в Дубае: тушение скандала <code>-{penalty} ₪</code>!",
            "Депутат свалил всю вину за недострой больницы на тебя: крупный штраф <code>-{penalty} ₪</code>!"
        ],
        "jackpot_phrases": [
            "💎 <b>ГОСЗАКАЗ ГОДА!</b> Выиграл генеральный подряд на постройку космодрома в степи! Освоено: <code>+{reward} ₪</code>!"
        ]
    }
}


def get_vacancies() -> Dict[str, Dict[str, Any]]:
    return WORK_VACANCIES


def execute_job_action(job_id: str, current_items: dict) -> Tuple[bool, int, str, Optional[str]]:
    """
    Executes job outcome with full RPG gear multipliers, set bonuses, milestones, and drops.
    Returns: (is_success, amount_change, text_message, item_dropped_key_or_none)
    """
    if job_id not in WORK_VACANCIES:
        return False, 0, "❌ Неизвестная вакансия.", None

    job = WORK_VACANCIES[job_id]
    now = int(time.time())
    work_timers = current_items.setdefault("work_cooldowns", {})
    last_time = work_timers.get(job_id, 0)
    passed = now - last_time

    # Cooldown Buffs: Slippers reduce cooldown by 20%
    base_cd = job["cooldown_sec"]
    if current_items.get("equipped_feet") == "feet_slippers":
        base_cd = int(base_cd * 0.8)

    if passed < base_cd:
        left_sec = base_cd - passed
        if left_sec >= 3600:
            h = left_sec // 3600
            m = (left_sec % 3600) // 60
            cd_str = f"{h} ч {m} мин"
        elif left_sec >= 60:
            cd_str = f"{left_sec // 60} мин"
        else:
            cd_str = f"{left_sec} сек"
        return False, 0, f"⏳ Кулдаун! Эта смена будет доступна через {cd_str}.", None

    # Check Requirements (Progressive shifts unlock)
    total_shifts = current_items.get("work_shifts", 0)
    req_shifts = job.get("required_shifts", 0)
    if total_shifts < req_shifts:
        return False, 0, f"🔒 Вакансия заблокирована! Требуется стаж: {req_shifts} смен (у тебя: {total_shifts}).", None

    # Calculate Salary Multiplier from Gear & Sets
    salary_mult = 1.0
    buff_notes = []

    # Individual Gear Buffs
    torso = current_items.get("equipped_torso")
    head = current_items.get("equipped_head")
    face = current_items.get("equipped_face")

    if torso == "body_wasserman":
        salary_mult += 0.25
        buff_notes.append("🦺 Жилетка Вассермана: +25% ЗП")
    if head == "hat_crown" and job_id in ["courier", "deputy", "scam"]:
        salary_mult += 0.20
        buff_notes.append("👑 Корона: +20% чаевых")
    if face in ["face_wasserman_glasses", "face_thug_glasses"] and job_id in ["captcha", "it_freelance", "spy"]:
        salary_mult += 0.15
        buff_notes.append("👓 Очки Интеллекта: +15% ЗП")

    # Set Bonuses
    try:
        from wardrobe_engine import get_active_set_bonus
        active_set = get_active_set_bonus(current_items)
        if active_set:
            if active_set["id"] == "set_wasserman":
                salary_mult += 0.40
                buff_notes.append("🦺 Сет Онотоле: +40% ЗП")
            elif active_set["id"] in ["set_gop_skuf", "set_skuf"]:
                salary_mult += 0.35
                buff_notes.append("🍺 Сет Скуфа: +35% получки")
            elif active_set["id"] == "set_neo":
                salary_mult += 0.25
                buff_notes.append("🕶️ Сет Нео: +25% ЗП")
    except Exception:
        active_set = None

    # Failure & Risk Calculation
    risk_pct = job.get("risk_pct", 0.0)
    if active_set and active_set["id"] in ["set_riot_police", "set_omon"]:
        risk_pct = 0.0  # Riot police immunity to work fines
        buff_notes.append("🪖 Спецназ: 0% штрафов")

    is_fail = (risk_pct > 0.0 and random.random() < risk_pct)
    if is_fail:
        penalty = job.get("penalty", 30)
        work_timers[job_id] = now
        fail_list = job.get("fail_phrases", ["🚨 Штраф за косяк на смене: -{penalty} ₪!"])
        raw_fail = random.choice(fail_list).format(penalty=penalty, reward=0)
        clean_fail = re.sub(r'<[^>]+>', '', raw_fail)
        return False, penalty, clean_fail, None

    # Success & Reward Calculation
    base_reward = random.randint(job["reward_range"][0], job["reward_range"][1])
    is_jackpot = random.random() < 0.04 and bool(job.get("jackpot_phrases"))

    if is_jackpot:
        mult = random.randint(2, 3)
        reward = int(base_reward * mult * salary_mult)
        work_timers[job_id] = now
        jp_tmpl = random.choice(job["jackpot_phrases"]).format(reward=reward, penalty=0)
        clean_msg = re.sub(r'<[^>]+>', '', jp_tmpl)
    else:
        reward = int(base_reward * salary_mult)
        work_timers[job_id] = now
        succ_list = job.get("phrases", ["✅ Успешно отработал смену: +{reward} ₪!"])
        raw_succ = random.choice(succ_list).format(reward=reward, penalty=0)
        clean_msg = re.sub(r'<[^>]+>', '', raw_succ)

    # Track Completed Shifts & Check Milestone Achievements
    total_shifts += 1
    current_items["work_shifts"] = total_shifts
    ach_note = ""
    try:
        from achievements_engine import check_and_unlock_achievement
        if total_shifts >= 1:
            unlocked, ach_info = check_and_unlock_achievement(current_items, "ach_first_work")
            if unlocked and ach_info:
                reward += ach_info.get('reward_cash', 0)
                ach_note += f" | 🏆 Ачивка: {ach_info['name']} (+{ach_info['reward_cash']} ₪)!"
        if total_shifts >= 10:
            unlocked, ach_info = check_and_unlock_achievement(current_items, "ach_work_10")
            if unlocked and ach_info:
                reward += ach_info.get('reward_cash', 0)
                ach_note += f" | 🏆 Ачивка: {ach_info['name']} (+{ach_info['reward_cash']} ₪)!"
        if total_shifts >= 50:
            unlocked, ach_info = check_and_unlock_achievement(current_items, "ach_work_50")
            if unlocked and ach_info:
                reward += ach_info.get('reward_cash', 0)
                ach_note += f" | 🏆 Ачивка: {ach_info['name']} (+{ach_info['reward_cash']} ₪)!"
        if total_shifts >= 100:
            unlocked, ach_info = check_and_unlock_achievement(current_items, "ach_work_100")
            if unlocked and ach_info:
                reward += ach_info.get('reward_cash', 0)
                ach_note += f" | 🏆 Ачивка: {ach_info['name']} (+{ach_info['reward_cash']} ₪)!"
    except Exception:
        pass

    # Check Random Item Drop (Anime set doubles drop rate)
    drop_rate_mult = 2.0 if (active_set and active_set["id"] == "set_anime") else 1.0
    if head == "hat_bag":
        drop_rate_mult *= 1.5

    dropped_item = None
    if job.get("item_drop") and random.random() < (job.get("item_drop_chance", 0.0) * drop_rate_mult):
        dropped_item = job["item_drop"]

    buff_suffix = f" (Шмот: {', '.join(buff_notes)})" if buff_notes else ""
    final_text = f"{clean_msg}{ach_note}{buff_suffix}"

    return True, reward, final_text, dropped_item
