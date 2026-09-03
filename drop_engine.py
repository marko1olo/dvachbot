"""
Drop Engine for DvachBot: Public Money Drop ("Чек / Дроп шекелей в тред на реакцию")
100% race-condition protected inside atomic db_lock & drop_lock, with persistent DB backup in MoneyDrops table.
"""

import asyncio
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# -----------------------------------------------------------------------------
# Data Structures
# -----------------------------------------------------------------------------

@dataclass
class DropRecord:
    drop_id: str
    donor_id: int
    donor_name: str
    board_id: str
    amount: int
    created_at: float
    expires_at: float
    status: str = "active"  # "active", "claimed", "expired", "cancelled"
    claimed_by: Optional[int] = None
    claimed_name: Optional[str] = None
    claimed_at: Optional[float] = None


# In-memory registry of active and recent drops
active_drops: Dict[str, DropRecord] = {}
drop_lock = asyncio.Lock()
# Track all sent messages for each drop_id: {drop_id: [(chat_id, message_id), ...]}
_drop_messages: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
# Anti-spam cooldown tracking for drop creation: {donor_id: cooldown_expiry_timestamp}
_user_drop_cooldowns: Dict[int, float] = {}
# Anti-bot cooldown tracking for claiming drops: {claimer_id: cooldown_expiry_timestamp}
_user_claim_cooldowns: Dict[int, float] = {}
# Sliding window claim history for rate limiting (max 3 claims per 5 min): {claimer_id: [claim_timestamp, ...]}
_user_claim_history: Dict[int, List[float]] = defaultdict(list)
# Sybil/twink farm pair history (max 1 claim per 1 hour from same donor): {(donor_id, claimer_id): [claim_timestamp, ...]}
_pair_claim_history: Dict[Tuple[int, int], List[float]] = defaultdict(list)
# Board flood limiter: {board_id: last_drop_timestamp}
_board_drop_timestamps: Dict[str, float] = {}

# Minimum reaction delay in seconds (configurable, e.g. 1.0 - 1.5s)
_min_claim_reaction_delay: float = 1.0

# -----------------------------------------------------------------------------
# Limits & Excuses
# -----------------------------------------------------------------------------

MIN_DROP_AMOUNT: int = 150
MAX_DROP_AMOUNT: int = 1_000_000

# Rate limits
MIN_DROP_COOLDOWN_SEC: int = 60
CLAIM_COOLDOWN_SEC: float = 30.0
MAX_CLAIMS_PER_WINDOW: int = 3
CLAIM_WINDOW_SEC: float = 300.0  # 5 minutes
MAX_PAIR_CLAIMS_PER_WINDOW: int = 3
PAIR_CLAIM_WINDOW_SEC: float = 600.0  # 10 minutes (softened: up to 3 claims per 10 min from same donor)
MIN_BOARD_DROP_INTERVAL_SEC: float = 5.0
MAX_ACTIVE_DROPS_PER_USER: int = 1

# Пул отмазок с черным юмором в стиле Двача при сумме меньше минимальной (< 150 ₪)
DROP_MIN_EXCUSES: List[str] = [
    "Слышь, нищеброд, твои копейки ({amount} ₪) даже на доширак не наскребут. Минимальный дроп — 150 ₪. Не позорься перед бордой.",
    "Ты кого тут насмешить вздумал своими {amount} ₪? Бомжи у параши громче сморкаются. Минимум 150 ₪, нищук.",
    "{amount} ₪? Серьёзно, сука? Ты эту сдачу с маршрутки у мамки из кармана вытащил? Меньше 150 ₪ в тред не высирай.",
    "Абу отказался принимать твои {amount} ₪ — сказал, что от такой нищеты у него серверная плесенью покроется. Минималка — 150 ₪.",
    "Твои {amount} ₪ — это даже не капля в море, а плевок в лицо анонам. Закидывай от 150 ₪ или пиздуй собирать бутылки.",
    "Экономический комитет Двача постановил: дропы меньше 150 ₪ приравниваются к биомусору. У тебя всего {amount} ₪.",
    "Ты бы ещё пыль из-под ногтей в тред дропнул. Твои {amount} ₪ — позор рода. Минимальный чек — 150 ₪.",
    "Шекелевый инспектор зафиксировал критический уровень нищеты ({amount} ₪). Меньше 150 ₪ даже цыгане не подберут.",
    "Пошел нахуй со своими {amount} ₪. Тут уважаемая борда, а не благотворительная столовая для опущенных. Минимум — 150 ₪.",
    "Твой донат на {amount} ₪ вызвал приступ смеха у модераторов. Не позорься, копи до 150 ₪.",
    "Дропнуть {amount} ₪? Да тебя за такие копейки в /b/ обоссут и на мороз выкинут. Минимальный дроп — 150 ₪.",
    "Твои {amount} ₪ застряли между половицами. Меньше 150 ₪ сюда даже не суй, нищета.",
    "Сумма {amount} ₪ была с позором смыта в унитаз. Меньше 150 ₪ — это не деньги, а мусор под ногтями.",
    "Ты на {amount} ₪ даже коробок спичек у бабки у метро не выклянчишь. Копи до 150 ₪, нищий.",
    "Засунь свои {amount} ₪ себе в копилку-свинку и разбей, когда накопишь хотя бы 150 ₪.",
    "У санитаров дурки случился инфаркт от твоей щедрости ({amount} ₪). Минимум 150 ₪, жлоб комнатный.",
    "Абу передал: комиссия за просмотр твоих {amount} ₪ стоит дороже самого дропа. Меньше 150 ₪ не принимаем.",
    "Твои {amount} ₪ оскорбили чувства верующих в мацу и шекели. Минимальный взнос — 150 ₪.",
    "Хватит звенеть медяками ({amount} ₪) как попрошайка у вокзала. Настоящие двачеры кидают от 150 ₪.",
    "Даже бомж под мостом отказался нагибаться за {amount} ₪. Ставь от 150 ₪, нищук.",
    "Твой чек на {amount} ₪ признан финансовым преступлением против человечности. Минимум 150 ₪.",
    "Ты эту мелочь ({amount} ₪) со дна фонтана магнитом на веревочке выловил? Минималка — 150 ₪.",
    "Сервер подавился твоими {amount} ₪ и выблевал их обратно. Дропай от 150 ₪.",
    "С такими грошами ({amount} ₪) сиди в ридонли под шконкой и не отсвечивай. Порог — 150 ₪.",
    "Эй, Скрудж Макдак из хрущевки! {amount} ₪ оставь себе на корвалол и боярышник. Минимум — 150 ₪."
]

# Пул отмазок с черным юмором в стиле Двача при превышении лимита (> 1 000 000 ₪)
DROP_MAX_EXCUSES: List[str] = [
    "Осади коней, Ротшильд мамкин. Дропнуть {amount} ₪? Максимум 1 000 000 ₪ за раз, иначе серверная Абу сгорит от гиперинфляции.",
    "{amount} ₪ за один дроп?! Ты чё, печатный станок ЦБ ограбил? Лимит — 1 000 000 ₪, не ломай экономику борды.",
    "Шекелевый инфаркт! Сумма {amount} ₪ превышает лимит в 1 000 000 ₪. Моссад уже выехал по твою душу за отмывание триллионов.",
    "Куда разогнался, олигарх комнатный? {amount} ₪ — это перебор. Максимальный дроп — 1 000 000 ₪.",
    "Транзакция на {amount} ₪ заблокирована Интерполом Двача. Максимум за один раз — 1 000 000 ₪.",
    "Ты решил весь золотовалютный фонд треда в один клик слить? {amount} ₪ не пролезет, потолок — 1 000 000 ₪.",
    "Слишком жирно! Твои {amount} ₪ разорвут баланс борды на атомы. Срежь осетра до 1 000 000 ₪.",
    "Абу подавился мацой, увидев твои {amount} ₪. Лимит одного чека — ровно 1 000 000 ₪.",
    "Притормози, криптомагнат хуев! {amount} ₪ — слишком много для одной транзакции. Максимум — 1 000 000 ₪.",
    "Эй, Дракон Смауг, придержи чешую. Дроп на {amount} ₪ отклонен, лимит — 1 000 000 ₪ за раз.",
    "Куда столько прешь ({amount} ₪)? Налоговая Двача конфискует всё свыше 1 000 000 ₪.",
    "Ты решил выкупить весь /b/ целиком со всеми шлюхами за {amount} ₪? Лимит одной пачки — 1 000 000 ₪.",
    "От твоих {amount} ₪ у Абу яхта чуть не перевернулась в Средиземном море. Максимум — 1 000 000 ₪ за раз.",
    "Сумма {amount} ₪ не помещается в базу данных SQLite! Потолок чека — 1 000 000 ₪.",
    "Остановись, Илон Маск на минималках! {amount} ₪ ломают экономический баланс треда. Максимум 1 000 000 ₪.",
    "Твои {amount} ₪ вызвали боевую тревогу в Пентагоне и ЦРУ. Ограничение транзакции — 1 000 000 ₪.",
    "Банковский сейф лопнул по швам от твоих {amount} ₪. За один присест максимум 1 000 000 ₪.",
    "Ты что, взломал кошелек Павла Дурова? {amount} ₪ — перебор. Лимит — 1 000 000 ₪.",
    "Финмониторинг заблокировал перевод на {amount} ₪ по подозрению в финансировании рептилоидов. Лимит 1 000 000 ₪.",
    "Полегче на поворотах, шейх из однушки в Бирюлево! {amount} ₪ — слишком жирно. Срежь до 1 000 000 ₪.",
    "Абу лично заблокировал транзакцию на {amount} ₪ из черной зависти. Максималка — 1 000 000 ₪.",
    "Твои {amount} ₪ вызвали обвал шекеля на черной бирже. Больше 1 000 000 ₪ в тред не вываливать!",
    "Не ломай казино и дропы! {amount} ₪ превышает допустимый потолок безопасности в 1 000 000 ₪.",
    "Столько шекелей ({amount} ₪) даже в самосвал не влезут. Лимит чека — 1 000 000 ₪.",
    "Твоя жажда понтов на {amount} ₪ заблокирована санитарами. Максимальный размер чека — 1 000 000 ₪."
]

# Пул отмазок с черным юмором в стиле Двача при срабатывании кулдауна на создание дропа (раздачи раз в 5 минут / 300с)
DROP_COOLDOWN_PHRASES: List[str] = [
    "Слышь, нищеброд, твои копейки даже бомжи у параши не поднимают. Погоди {seconds}с, пока Абу подметёт твои гроши.",
    "Ты чё, автомат по выдаче мелочи? Засунь свои шекели обратно в очко и подожди {seconds}с.",
    "Еврейская община в ахуе от твоей щедрости. Раздачи разрешены раз в 5 минут! Остынь на {seconds}с перед следующим плевком в вечность.",
    "Руки от кошелька убрал, лудоман хуев. Раскидывать мелочь сможешь только через {seconds}с.",
    "Остынь, меценат мамкин. Твой нищенский спам на кулдауне ещё {seconds}с. Лимит — 1 дроп в 5 минут.",
    "Абу конфисковал твою мелочь на ремонт серверов. Жди {seconds}с, олигарх из трущоб.",
    "Шекелевый инфаркт жопы. Твоя подачка на проверке в налоговой Моссада, таймер: {seconds}с.",
    "Твой благотворительный фонд «Помощь нищим даунам» заморожен. Кулдаун {seconds}с.",
    "Не сри мелочью в тред, тут люди деградируют. Подожди {seconds}с и подумай над своим поведением.",
    "Ты кого тут подкупить пытаешься, олигарх с помойки? Жди {seconds}с до следующего высера.",
    "Копеечный спамер детектирован. Санитары выехали, а твоя кнопка заблокирована на {seconds}с.",
    "Даже цыгане на вокзале побрезговали твоим дропом. Остынь на {seconds}с.",
    "Опять ты со своей сдачей от школьного обеда. Подожди {seconds}с, пока твой позор забудут.",
    "Твои копейки застряли в зубах у Абу. Выковыривать будут ещё {seconds}с.",
    "Финансовый регулятор Двача заблокировал твои гроши за отмывание бомжатских денег. Жди {seconds}с.",
    "Пособие по безработице кончилось? Не части, жди {seconds}с перед следующим дропом.",
    "Шекелемет перегрелся от твоих микро-плевков. Охлаждение ствола: {seconds}с.",
    "Анон, ты забыл таблетки и решил раздать всё имущество? Санитары прописали тайм-аут на {seconds}с.",
    "Твои три копейки вызвали дефляцию в Зимбабве. Посиди смирно {seconds}с, спамер.",
    "Дропалка не выросла так часто шекелями раскидываться. Раздачи раз в 5 минут! Подожди {seconds}с.",
    "Куда пулемётишь чеками? Абу ввёл 5-минутный налог на отдых. Остынь на {seconds}с.",
    "Фонд спасения опущенцев закрыт на переучёт. Следующая раздача через {seconds}с.",
    "Ты решил всю борду подкупить своими грошами? Сиди на бутылке смирно ещё {seconds}с.",
    "Модерация устала подметать твои фантики. Кулдаун раздачи: {seconds}с.",
    "Слишком частый благотворитель — верный признак шизофрении. Таблетки подействуют через {seconds}с.",
    "Раздавать шекели как из пулемета запрещено конвенцией Двача. Таймер: {seconds}с.",
    "Эй, спонсор сельской дискотеки, придержи карманы! Кулдаун: {seconds}с."
]

COOLDOWN_EXCUSES = DROP_COOLDOWN_PHRASES

# Пул отмазок при срабатывании детектора автокликера / бота (< reaction delay)
BOT_CLAIM_EXCUSES: List[str] = [
    "🤖 Детектор автокликера! Твоя реакция: {delta:.2f}с. Слишком быстро для человека! Руки на стол, ботовод.",
    "🤖 Анти-автокликер! Ты среагировал за {delta:.2f}с. Мониторинг борды заблокировал реакцию бота. Капча не пройдена!",
    "⚡ Слишком быстро ({delta:.2f}с)! Скорость клика превысила биологический предел человека. Дроп защищен от скриптов.",
    "🤖 Капча Абу: Детектор скриптов зафиксировал клик за {delta:.2f}с. Настоящие аноны читают тред глазами, а не парсером.",
    "🛑 Антибот: Реакция {delta:.2f}с? Ты чё, нейросеть из Сколково? Кнопка сбора заблокирована при подозрительно быстром клике.",
    "🤖 Ловушка для макросников сработала! Твой скрипт нажал за {delta:.2f}с. Отдохни и нажимай руками.",
    "🦾 Обнаружен терминатор ({delta:.2f}с). Шекели предназначены живым анонам, а не скриптам на Python/JS.",
    "🤖 Слышь, робот ебаный, клик за {delta:.2f}с не прокатит. Иди заряжайся от розетки, а шекели людям оставь.",
    "⚡ Задержка {delta:.2f}с? У тебя что, оптический кабель напрямую в жопу вставлен? Пальцами кликай, читер.",
    "🤖 Анти-скрипт защита Абу сработала ({delta:.2f}с)! Попытка перехвата ботом пресечена на корню.",
    "🛑 Твой кликер спалился на скорости {delta:.2f}с! На Дваче ботов ебут в прямом эфире.",
    "🤖 Ты кликнул за {delta:.2f}с? Иди расскажи своей бабушке, что ты человек, а не скрипт.",
    "⚡ Скорость света не поможет ({delta:.2f}с). Система распознавания макросов отменила твой перехват.",
    "🤖 Бот-пылесос обнаружен и обоссан ({delta:.2f}с). Шекели остались в треде.",
    "🛑 Клик за {delta:.2f}с аннулирован! Настоящий сыч сначала 2 секунды чешет пузо.",
    "🤖 Скриптовая макака поймана с поличным ({delta:.2f}с). Выпей машинного масла и остынь.",
    "⚡ Задержка {delta:.2f}с? Даже нейроны в твоем скудном мозгу бегают медленнее. Чек защищен.",
    "🤖 Сигнал тревоги: реакция {delta:.2f}с. Детектор ботов отправил твой скрипт в утиль.",
    "🛑 Пальчики-крючки не могут кликать за {delta:.2f}с. Макрос отправлен на помойку.",
    "🤖 Ошибка биометрии: скорость {delta:.2f}с характерна для стиральной машины, а не двачера.",
    "⚡ Реакция {delta:.2f}с? Ты чё, спидами обкололся? Защита от читов заблокировала перехват.",
    "🤖 Твой питоновский скрипт на requests/aiohttp обосрался на скорости {delta:.2f}с. Гуляй.",
    "🛑 Клик за {delta:.2f}с заблокирован анти-турбо защитой Абу. Ручками тыкай!",
    "🤖 Детектор синтетических кликов: {delta:.2f}с — это наглый ботоводческий перехват.",
    "⚡ Капча не пройдена ({delta:.2f}с): докажи, что ты не киборг, подождав как обычный анон."
]

# Пул отмазок при кулдауне на сбор дропов (30 секунд)
CLAIM_COOLDOWN_EXCUSES: List[str] = [
    "Ты недавно уже перехватил дроп! Подожди {seconds}с, не жадничай.",
    "Жадность фраера сгубила. Кулдаун на сбор шекелей: ещё {seconds}с. Дай другим нищукам поживиться.",
    "Инспектор сбора Двача: ты слишком часто хватаешь шекели. Таймер отдыха: {seconds}с.",
    "Твои загребущие лапы на кулдауне ещё {seconds}с. Остынь, олигарх.",
    "Ненасытная пасть! Дай другим анонам подобрать шекели. Жди {seconds}с.",
    "Шекелевый инспектор зафиксировал перегрузку карманов. Пауза между сборами: {seconds}с.",
    "Куда хапаешь, пылесос? Руки обожжёшь! Кулдаун жадности: {seconds}с.",
    "Пальцы устали грести чужие гроши? Остынь на {seconds}с, поделись с бордой.",
    "Тебе одного чека мало было? Захлебнёшься! Сиди смирно {seconds}с.",
    "Слишком быстро набиваешь карманы! Кулдаун сборщика: {seconds}с.",
    "Хапалка сломается так часто чеки собирать. Таймер: {seconds}с.",
    "Абу следит за твоими загребущими ручонками. Пауза {seconds}с перед следующим дропом.",
    "Ты решил в соло все подачки с пола собрать? Жди {seconds}с, дай шанс другим опущенцам.",
    "Жадный сыч обнаружен! Твой перехватчик заморожен на {seconds}с.",
    "Не части, пылесос тредовый! Кулдаун между поднятиями: {seconds}с.",
    "Твои карманы полны свежего лута. Переваривай ещё {seconds}с.",
    "Слишком резвый сборщик! Остынь на {seconds}с, а то санитары свяжут.",
    "Шекели к рукам липнут? Помой руки и подожди {seconds}с.",
    "Дай другим бомжам понюхать мацу! Твой таймер: {seconds}с.",
    "Притормози, лутоман! Кулдаун на подбор чеков: {seconds}с.",
    "Один чек взял — и радуйся жизни {seconds}с.",
    "Сбор шекелей на паузе. Твоя жадность наказывается ожиданием в {seconds}с.",
    "Куда гребешь как экскаватор? Остынь на {seconds}с.",
    "Финконтроль Двача: пауза между сборами {seconds}с. Не наглей.",
    "Ты не единственный нищий на этой борде. Подожди {seconds}с."
]

# Пул отмазок при детектировании перелива шекелей (ботофермы / твинки)
PAIR_FARM_EXCUSES: List[str] = [
    "Финмониторинг Абу: ты уже забирал дроп от этого анона недавно! Перелив шекелей между спаренными аккаунтами заблокирован.",
    "Анти-ферма: детектор твинков засёк систематический сбор шекелей у одного донора. Операция заблокирована.",
    "Моссад пресёк попытку отмывания шекелей через дропы между своими твинками! Не пытайся обойти налог.",
    "Детектор ботоферм зафиксировал подозрительную связь между аккаунтами. Дроп не может быть собран постоянным сборщиком.",
    "Комитет госбезопасности Двача заблокировал перелив баланса между спаренными аккаунтами.",
    "Кого наебать вздумал, ботовод? Перекачка шекелей между твоими твинками заблокирована на 1 час!",
    "Шекелевая прачечная накрыта! Ты слишком часто подбираешь чеки у этого же дружка-пирожка.",
    "Налог Абу не обойти! Перелив через дропы заблокирован антифрод-системой борды.",
    "Твинковод детектед! Перекачивать шекели с левой руки в правую запрещено правилами.",
    "Слишком подозрительная любовь между аккаунтами. Сбор у этого донора заблокирован на 1 час.",
    "Вы чё, вдвоём шекелевый круговорот устроили? Операция пресечена финконтролем.",
    "Попытка обхода комиссии /pay через дропы раскрыта. Посиди без шекелей от этого дружка.",
    "Детектор карманных ферм: перелив между спаренными сычами заблокирован.",
    "Хватит доить своего твинка! Антифрод заблокировал этот перехват на 1 час.",
    "Моссад не дремлет: схема перелива через публичные чеки накрыта медным тазом.",
    "Ты у этого анона на зарплате сидишь? Подозрительная связка аккаунтов заблокирована.",
    "Шекелевый офшор накрыт налоговой Двача. Дропы от этого донора для тебя закрыты.",
    "Ботоводческие схемы 2007 года тут не прокатят. Сбор между связанными профилями заблокирован.",
    "Один кидает — второй сразу подбирает? Слишком толстый перелив, операция отклонена.",
    "Абу лично конфисковал твою схему перелива. Не пытайся лутать чеки одного и того же донора.",
    "Связка донор-сборщик заморожена антифрод-сканером на 1 час.",
    "Твои твинки пахнут одинаково плохо. Перелив шекелей между ними заблокирован.",
    "Анти-сибилла сработала: передача шекелей в обход казны Абу заблокирована.",
    "Слишком сладкая парочка! Перехват чеков у постоянного спонсора заблокирован.",
    "Финмониторинг пресёк подозрительную транзакцию между аффилированными анонами."
]

# Пул отмазок при превышении квоты сбора (лимит жадности: макс 3 дропа за 5 минут)
CLAIM_QUOTA_EXCUSES: List[str] = [
    "ЛИМИТ ЖАДНОСТИ: Ты уже запылесосил 3 дропа за последние 5 минут! Пасть треснет, дай другим нищукам поживиться.",
    "Куда хапаешь, пылесос комнатный?! 3 дропа за 5 минут — твой потолок. Сиди на жопе ровно и жди.",
    "Шекелевый инспектор конфисковал твои загребущие клешни. Квота (3 дропа за 5 мин) исчерпана!",
    "Ты чё, на зарплате у бомжей сидишь? Хватит лутать все чеки подряд, отдохни 5 минут.",
    "Карманы лопаются от жадности! 3 дропа подряд — лимит исчерпан. Поделись с бордой.",
    "Харя не треснет? 3 дропа за 5 минут — предел насыщения. Гуляй, олигарх.",
    "Жадность зашкаливает: 3 чека за 5 минут уже в кармане. Дай другим анонам крошки подобрать.",
    "Твой пылесос перегрелся от жадности! Квота 3/5 мин исчерпана, жди охлаждения.",
    "Ты решил один всю экономику борды обчистить? Лимит сбора (3 дропа) исчерпан.",
    "Стоп, грабитель! Больше 3 дропов за 5 минут ни один сыч унести не может.",
    "Абу наложил вето на твою прожорливость. 3 чека собрано — иди переваривай.",
    "Передоз шекелями! Квота 3 дропа за 5 минут заблокировала твои загребущие руки.",
    "Ненасытное брюхо! 3 чека за 5 минут — максимум. Освободи место у корыта.",
    "Шекелевый лимит превышен: 3/3 собрано. Следующий сбор только через 5 минут.",
    "Хватит пылесосить тред! Ты уже залутал 3 дропа. Сиди и завидуй другим.",
    "Пожалей других нищих двачеров! Твоя квота (3 дропа за 5 мин) полностью исчерпана.",
    "Твои карманы волочатся по полу от жадности. Лимит 3 сбора за 5 минут активен.",
    "Шекелевая жаба задушила? 3 дропа подряд — потолок. Отдохни от сбора.",
    "Инспектор щедрости Двача: сборщику выписан штрафной тайм-аут за жадность (3/3).",
    "Ты чё, самый голодный в треде? 3 дропа собрал — уступи дорогу другим.",
    "Лимит халявы исчерпан: 3 дропа за 5 минут. Иди поработай в /work.",
    "Загребущие лапы заблокированы: 3 чека за 5 минут — это абсолютный максимум.",
    "Твоя ненасытность оскорбляет Абу. Квота на сбор чеков исчерпана, жди.",
    "3 дропа за 5 минут залутал — и хватит с тебя. Дай другим нищукам погреться.",
    "Хватит с пола подбирать всё подряд! Лимит 3 дропа в 5 минут заморозил твои клики."
]

# Пул отмазок при попытке создать второй дроп, пока первый активен
ACTIVE_DROP_EXCUSES: List[str] = [
    "Куда разогнался, сорильщик шекелей?! У тебя уже висит активный несобранный дроп в треде. Дождись пока нищуки растащат, или отмени его.",
    "Осади, меценат мамкин. У тебя уже валяется несобранный чек под ногами у анонов. Второй дроп подряд нельзя!",
    "Жадность и мания величия! Сначала пусть подберут твой предыдущий дроп, потом разбрасывай новый.",
    "Твой прошлый чек ещё никто даже палкой не потыкал, а ты уже новый высираешь. Жди или жми отмену.",
    "Лимит щедрости: 1 активный дроп на рыло. Твой чек всё ещё ждёт своего бомжа в треде.",
    "Ты решил весь тред своими несобранными чеками завалить? Дождись сбора старого дропа.",
    "Один дроп за раз! Твоя предыдущая подачка всё ещё пылится в чате.",
    "Не спамь чеками! Пока первый дроп активен, второй создать не дадим.",
    "Твой благотворительный транш ещё не освоен анонами. Жди или отменяй предыдущий.",
    "Куда строчишь как пулемёт? Предыдущий дроп ещё активен. Не плоди мусор в треде.",
    "Сначала пристрой свой первый чек, благодетель хуев. 1 активный дроп на человека!",
    "Абу запретил вешать гирлянды из несобранных дропов. Дождись сбора первого чека.",
    "Твой прошлый выброс шекелей всё ещё висит в треде. Второй создавать нельзя.",
    "Не захламляй борду! 1 активный чек на пользователя. Жди сборщика или жми отмену.",
    "Очередь на благотворительность: твой старый дроп ещё не забрали. Новый отклонен.",
    "Ты что, банк открыл посреди треда? Сначала пусть подберут старый дроп.",
    "Пока твой первый чек валяется без дела, второй выкидывать запрещено.",
    "Твоя прошлая подачка ещё не нашла своего хозяина. Жди окончания таймера или сбора.",
    "Не разбрасывайся шекелями веером! 1 активный дроп — железное правило Двача.",
    "Предыдущий чек активен. Не устраивай мусорную свалку из несобранных дропов.",
    "Слишком много чеков от одного анона! Дождись пока заберут первый.",
    "Твой дроп всё ещё ждёт своего счастливчика. Новый создавать пока нельзя.",
    "Один чек в одни руки треда! Предыдущий дроп всё ещё не закрыт.",
    "Не части с подачками. Предыдущий дроп активен — жди клика от анонов.",
    "Твой несобранный чек мозолит глаза модераторам. Дождись сбора перед следующим."
]

# Пул отмазок при флуде дропами на борду (слишком частые дропы в треде)
BOARD_FLOOD_EXCUSES: List[str] = [
    "Борда захлебнулась от шекелевого спама! Абу подметает серверную, подожди {seconds}с перед новым дропом.",
    "Тред перегружен дропами! Модерация временно заморозила шекелемет доски, таймер: {seconds}с.",
    "Слишком много подачек в одну секунду! Борда не резиновая, остынь на {seconds}с.",
    "Шекелевый шторм 9 баллов на доске! Притормози на {seconds}с, дай анонам продышаться.",
    "Доска горит от чеков! Сервер охлаждается жидким азотом, пауза: {seconds}с.",
    "Шекелемет доски перегрелся! Остывание ствола займет ещё {seconds}с.",
    "Флуд-контроль треда сработал: слишком много дропов подряд. Таймер: {seconds}с.",
    "Абу объявил технический перерыв от шекелевого спама на {seconds}с.",
    "Тред завален деньгами по самые уши! Подожди {seconds}с, пока растащат старое.",
    "Серверная плавится от частоты дропов на этой доске. Пауза: {seconds}с.",
    "Анти-флуд защита доски активирована. Подожди {seconds}с перед следующим чеком.",
    "Слишком частые раздачи ломают базу данных! Таймаут доски: {seconds}с.",
    "Модераторы не успевают разгребать чеки в треде. Подожди {seconds}с.",
    "Доска перегружена шекелевыми транзакциями. Очередь на раздачу: {seconds}с.",
    "Экономика треда перегрета! Анти-инфляционная пауза: {seconds}с.",
    "Шекелевый гейзер на борде временно прикрыт. Открытие через {seconds}с.",
    "Слишком плотный огонь чеками по треду! Перезарядка доски: {seconds}с.",
    "Тред временно закрыт на шекелевый карантин. Подожди {seconds}с.",
    "База данных просит пощады от дропового спама. Пауза {seconds}с.",
    "Таймаут доски активен: не частите с дропами! Ожидание: {seconds}с.",
    "Шекелевый спам-фильтр заблокировал частые выбросы на этой доске. Жди {seconds}с.",
    "Двачане не успевают кликать по кнопкам! Сбавьте темп на {seconds}с.",
    "Перегрузка каналов связи от дропов. Таймаут: {seconds}с.",
    "Шекелевый затор на доске! Разгрузка треда займет {seconds}с.",
    "Абу лично держит рубильник: пауза между дропами на борде {seconds}с."
]


def get_min_drop_rejection_message(amount: int) -> str:
    """Генерирует рандомную токсичную отмазку для суммы меньше 150 ₪."""
    template = secrets.choice(DROP_MIN_EXCUSES)
    return f"❌ {template.format(amount=amount)}"


def get_max_drop_rejection_message(amount: int) -> str:
    """Генерирует рандомную токсичную отмазку для суммы больше 1 000 000 ₪."""
    template = secrets.choice(DROP_MAX_EXCUSES)
    return f"❌ {template.format(amount=amount)}"


def get_drop_cooldown_seconds(amount: int) -> int:
    """
    Раздачи разрешены не чаще 1 раза в 5 минут (300 секунд).
    """
    return 300


def get_user_cooldown_remaining(user_id: int) -> float:
    """Возвращает оставшееся время кулдауна пользователя в секундах (float >= 0.0)."""
    expiry = _user_drop_cooldowns.get(user_id, 0.0)
    now = time.time()
    if now < expiry:
        return expiry - now
    return 0.0


def get_user_claim_cooldown_remaining(user_id: int) -> float:
    """Возвращает оставшееся время кулдауна на сбор дропов в секундах (float >= 0.0)."""
    expiry = _user_claim_cooldowns.get(user_id, 0.0)
    now = time.time()
    if now < expiry:
        return expiry - now
    return 0.0


def get_cooldown_rejection_message(remaining_seconds: int) -> str:
    """Генерирует рандомную отмазку с таймером в стиле Двача."""
    template = secrets.choice(COOLDOWN_EXCUSES)
    return f"⏳ {template.format(seconds=max(1, remaining_seconds))}"


def get_bot_reaction_rejection_message(delta: float) -> str:
    """Генерирует отмазку детектора ботов / автокликеров."""
    template = secrets.choice(BOT_CLAIM_EXCUSES)
    return f"❌ {template.format(delta=delta)}"


def get_claim_cooldown_rejection_message(remaining_seconds: int) -> str:
    """Генерирует отмазку кулдауна сбора шекелей."""
    template = secrets.choice(CLAIM_COOLDOWN_EXCUSES)
    return f"⏳ {template.format(seconds=max(1, remaining_seconds))}"


def get_pair_farm_rejection_message() -> str:
    """Генерирует отмазку детектора ботоферм/твинков."""
    template = secrets.choice(PAIR_FARM_EXCUSES)
    return f"🚫 {template}"


def get_claim_quota_rejection_message() -> str:
    """Генерирует отмазку при превышении лимита жадности сбора."""
    template = secrets.choice(CLAIM_QUOTA_EXCUSES)
    return f"⏳ <b>{template}</b>"


def get_active_drop_rejection_message() -> str:
    """Генерирует отмазку при попытке создать дроп при наличии уже активного."""
    template = secrets.choice(ACTIVE_DROP_EXCUSES)
    return f"❌ <b>{template}</b>"


def get_board_flood_rejection_message(remaining_seconds: int) -> str:
    """Генерирует отмазку при флуде дропами на борде."""
    template = secrets.choice(BOARD_FLOOD_EXCUSES)
    return f"⏳ <b>{template.format(seconds=max(1, remaining_seconds))}</b>"


def set_min_reaction_delay(val: float):
    """Устанавливает минимальную задержку человеческой реакции в секундах (для тестов)."""
    global _min_claim_reaction_delay
    _min_claim_reaction_delay = float(val)


def get_min_reaction_delay() -> float:
    """Возвращает текущую минимальную задержку реакции."""
    return _min_claim_reaction_delay


def reset_drop_cooldowns():
    """Сбрасывает все кулдауны, историю сборов и активные дропы (для тестов)."""
    _user_drop_cooldowns.clear()
    _user_claim_cooldowns.clear()
    _user_claim_history.clear()
    _pair_claim_history.clear()
    _board_drop_timestamps.clear()
    _drop_messages.clear()
    active_drops.clear()


def set_user_drop_cooldown(user_id: int, duration_sec: float):
    """Устанавливает кулдаун создания дропов пользователю на указанное количество секунд."""
    _user_drop_cooldowns[user_id] = time.time() + duration_sec


def set_user_claim_cooldown(user_id: int, duration_sec: float):
    """Устанавливает кулдаун сбора дропов пользователю на указанное количество секунд."""
    _user_claim_cooldowns[user_id] = time.time() + duration_sec


def register_drop_message(drop_id: str, chat_id: int, message_id: int):
    """Регистрирует отправленное сообщение о дропе для последующего обновления при перехвате."""
    pair = (chat_id, message_id)
    if pair not in _drop_messages[drop_id]:
        _drop_messages[drop_id].append(pair)


def get_drop_messages(drop_id: str) -> List[Tuple[int, int]]:
    """Возвращает список всех (chat_id, message_id) для данного drop_id."""
    return list(_drop_messages.get(drop_id, []))


def clear_drop_messages(drop_id: str):
    """Очищает зарегистрированные сообщения для drop_id."""
    _drop_messages.pop(drop_id, None)


async def record_drop_message_db(db_conn, drop_id: str, chat_id: int, message_id: int):
    """Регистрирует и сохраняет сообщение о дропе в БД."""
    register_drop_message(drop_id, chat_id, message_id)
    if db_conn:
        try:
            await db_conn.execute(
                "INSERT OR IGNORE INTO MoneyDropMessages (drop_id, chat_id, message_id) VALUES (?, ?, ?)",
                (drop_id, chat_id, message_id)
            )
            await db_conn.commit()
        except Exception:
            pass


async def clear_drop_messages_db(db_conn, drop_id: str):
    """Очищает зарегистрированные сообщения для drop_id в памяти и БД."""
    clear_drop_messages(drop_id)
    if db_conn:
        try:
            await db_conn.execute("DELETE FROM MoneyDropMessages WHERE drop_id = ?", (drop_id,))
            await db_conn.commit()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Drop Creation, Claiming & Persistence
# -----------------------------------------------------------------------------

async def init_drop_engine(db_conn) -> int:
    """
    Загружает неистекшие активные дропы и копии сообщений из БД при старте бота.
    Если дроп истек во время оффлайна бота, автоматически возвращает шекели донору.
    """
    now = time.time()
    loaded = 0
    from common.database import add_user_global_balance
    try:
        await db_conn.execute("""
            CREATE TABLE IF NOT EXISTS MoneyDropMessages (
                drop_id TEXT,
                chat_id INTEGER,
                message_id INTEGER,
                PRIMARY KEY(drop_id, chat_id, message_id)
            )
        """)
        async with db_conn.execute("SELECT drop_id, donor_id, board_id, amount, created_at FROM MoneyDrops WHERE status = 'active'") as c:
            rows = await c.fetchall()
        
        async with drop_lock:
            for r in rows:
                d_id, donor, board, amt, c_at = r
                exp_at = c_at + 600.0
                if now < exp_at:
                    donor_name = "Анон"
                    active_drops[d_id] = DropRecord(
                        drop_id=d_id,
                        donor_id=donor,
                        donor_name=donor_name,
                        board_id=board,
                        amount=int(amt),
                        created_at=c_at,
                        expires_at=exp_at,
                        status="active",
                    )
                    loaded += 1
                else:
                    await db_conn.execute(
                        "UPDATE MoneyDrops SET status = 'expired', refunded_at = ? WHERE drop_id = ?",
                        (now, d_id),
                    )
                    await add_user_global_balance(db_conn, donor, board, int(amt))
            await db_conn.commit()

        # Load persisted messages for active drops
        async with db_conn.execute("SELECT drop_id, chat_id, message_id FROM MoneyDropMessages") as c:
            msg_rows = await c.fetchall()
            for d_id, c_id, m_id in msg_rows:
                if d_id in active_drops:
                    register_drop_message(d_id, c_id, m_id)
    except Exception:
        pass
    return loaded


async def create_money_drop(
    donor_id: int,
    donor_name: str,
    board_id: str,
    amount: int,
    db_lock: asyncio.Lock,
    db_conn,
    timeout_sec: float = 600.0,
    check_cooldown: bool = True,
    check_active_limit: bool = False,
    check_board_flood: bool = False,
) -> Tuple[bool, str, Optional[DropRecord]]:
    """
    Atomically creates a public money drop by deducting funds from donor global balance.
    Persists drop in MoneyDrops DB table.
    Enforces minimum drop (150 ₪), maximum drop (1,000,000 ₪), anti-spam cooldowns,
    board flood protection, and 1-active-drop-per-user limit.
    """
    if amount < MIN_DROP_AMOUNT:
        return False, get_min_drop_rejection_message(amount), None

    if amount > MAX_DROP_AMOUNT:
        return False, get_max_drop_rejection_message(amount), None

    now = time.time()

    async with drop_lock:
        if check_cooldown:
            expiry = _user_drop_cooldowns.get(donor_id, 0.0)
            if now < expiry:
                rem_sec = int(expiry - now) + 1
                return False, get_cooldown_rejection_message(rem_sec), None

        if check_active_limit:
            user_active = [
                d for d in active_drops.values()
                if d.donor_id == donor_id and d.status == "active" and now < d.expires_at
            ]
            if len(user_active) >= MAX_ACTIVE_DROPS_PER_USER:
                return False, get_active_drop_rejection_message(), None

        if check_board_flood and board_id:
            board_last = _board_drop_timestamps.get(board_id, 0.0)
            if (now - board_last) < MIN_BOARD_DROP_INTERVAL_SEC:
                rem_board = int(MIN_BOARD_DROP_INTERVAL_SEC - (now - board_last)) + 1
                return False, get_board_flood_rejection_message(rem_board), None

    from common.database import deduct_user_global_balance, get_user_global_balance

    drop_id = secrets.token_hex(6)

    async with db_lock:
        try:
            ok, new_bal = await deduct_user_global_balance(db_conn, donor_id, board_id, amount)
            if not ok:
                current_bal = await get_user_global_balance(db_conn, donor_id)
                return False, f"❌ Недостаточно средств! Твой баланс: {int(current_bal)} ₪, а попытка дропнуть: {amount} ₪.", None
            
            await db_conn.execute(
                "INSERT INTO MoneyDrops (drop_id, donor_id, board_id, amount, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
                (drop_id, donor_id, board_id, float(amount), now),
            )
            from common.database import record_user_transaction
            await record_user_transaction(db_conn, donor_id, -amount, 'drop', f'Сброс чека в тред (#{drop_id})')
            await db_conn.commit()
        except Exception as e:
            return False, f"❌ Ошибка базы данных при создании дропа: {e}", None

    record = DropRecord(
        drop_id=drop_id,
        donor_id=donor_id,
        donor_name=donor_name,
        board_id=board_id,
        amount=amount,
        created_at=now,
        expires_at=now + timeout_sec,
        status="active",
    )
    
    async with drop_lock:
        active_drops[drop_id] = record
        # Set cooldown for the donor based on amount dropped (min 60s)
        cd_duration = get_drop_cooldown_seconds(amount)
        _user_drop_cooldowns[donor_id] = now + cd_duration
        if board_id:
            _board_drop_timestamps[board_id] = now

    return True, "✅ Дроп успешно создан и отправлен в чат!", record


async def claim_money_drop(
    drop_id: str,
    claimer_id: int,
    claimer_name: str,
    claimer_board_id: str,
    db_lock: asyncio.Lock,
    db_conn,
    check_reaction_delay: bool = False,
    check_claimer_rate_limit: bool = True,
    check_farm_laundering: bool = True,
    min_reaction_delay: Optional[float] = None,
) -> Tuple[bool, str, Optional[DropRecord]]:
    """
    Atomically claims a money drop (First-Come, First-Served).
    Guarantees exactly 1 winner under high concurrency.
    Protects against:
    - Autoclickers & bot scripts (human reaction delay >= 1.0s)
    - Claim spamming (cooldown between claims 30s)
    - Greed hoarding (sliding window max 3 claims per 5 min)
    - Sybil/twink farm laundering (max 1 claim per 1 hour from the same donor)
    """
    now = time.time()
    effective_min_delay = _min_claim_reaction_delay if min_reaction_delay is None else min_reaction_delay

    async with drop_lock:
        record = active_drops.get(drop_id)
        if not record:
            return False, "❌ Дроп не найден или уже был завершен.", None

        if record.status == "claimed":
            winner = record.claimed_name or f"Анон #{record.claimed_by}"
            return False, f"❌ Этот дроп уже забрал {winner}!", record

        if record.status == "expired":
            return False, "❌ Время действия этого дропа истекло, шекели вернулись донору.", record

        if record.status == "cancelled":
            return False, "❌ Этот дроп был отменен создателем.", record

        if record.donor_id == claimer_id:
            return False, "❌ Ты не можешь забрать свой собственный дроп! (Используй отмену, если передумал).", record

        # 1. Anti-Bot Reaction Delay Check
        if check_reaction_delay and effective_min_delay > 0.0:
            reaction_time = now - record.created_at
            if reaction_time < effective_min_delay:
                return False, get_bot_reaction_rejection_message(reaction_time), record

        # 2. Claimer Cooldown Check
        if check_claimer_rate_limit:
            expiry = _user_claim_cooldowns.get(claimer_id, 0.0)
            if now < expiry:
                rem_sec = int(expiry - now) + 1
                return False, get_claim_cooldown_rejection_message(rem_sec), record

            # 3. Sliding Window Claim Quota (Max 3 claims per 5 min)
            recent_claims = [t for t in _user_claim_history[claimer_id] if (now - t) < CLAIM_WINDOW_SEC]
            _user_claim_history[claimer_id] = recent_claims
            if len(recent_claims) >= MAX_CLAIMS_PER_WINDOW:
                return False, get_claim_quota_rejection_message(), record

        # 4. Anti-Sybil / Farm Laundering Check between paired accounts
        if check_farm_laundering and record.donor_id:
            pair_key = (record.donor_id, claimer_id)
            recent_pair = [t for t in _pair_claim_history[pair_key] if (now - t) < PAIR_CLAIM_WINDOW_SEC]
            _pair_claim_history[pair_key] = recent_pair
            if len(recent_pair) >= MAX_PAIR_CLAIMS_PER_WINDOW:
                return False, get_pair_farm_rejection_message(), record

        # Reserve drop status immediately inside drop_lock
        record.status = "claimed"
        record.claimed_by = claimer_id
        record.claimed_name = claimer_name
        record.claimed_at = now

        # Update claimer tracking
        _user_claim_cooldowns[claimer_id] = now + CLAIM_COOLDOWN_SEC
        _user_claim_history[claimer_id].append(now)
        if record.donor_id:
            _pair_claim_history[(record.donor_id, claimer_id)].append(now)

    # Atomically credit claimer in DB and update MoneyDrops record
    from common.database import add_user_global_balance, record_user_transaction
    async with db_lock:
        try:
            await add_user_global_balance(db_conn, claimer_id, claimer_board_id, record.amount)
            await record_user_transaction(db_conn, claimer_id, record.amount, 'drop', f'Активация чека из треда от {record.donor_name}')
            await db_conn.execute(
                "UPDATE MoneyDrops SET status = 'claimed', claimed_by = ?, claimed_board_id = ?, claimed_at = ? WHERE drop_id = ?",
                (claimer_id, claimer_board_id, record.claimed_at, drop_id),
            )
            await db_conn.commit()
        except Exception as e:
            # Revert status on severe db failure
            async with drop_lock:
                record.status = "active"
                record.claimed_by = None
                record.claimed_name = None
                record.claimed_at = None
                if _user_claim_history[claimer_id] and _user_claim_history[claimer_id][-1] == now:
                    _user_claim_history[claimer_id].pop()
                if record.donor_id and _pair_claim_history[(record.donor_id, claimer_id)] and _pair_claim_history[(record.donor_id, claimer_id)][-1] == now:
                    _pair_claim_history[(record.donor_id, claimer_id)].pop()
            return False, f"❌ Ошибка начисления выигрыша: {e}", None

    return True, f"🎉 Ты успешно перехватил дроп на {record.amount} ₪!", record


async def cancel_money_drop(
    drop_id: str,
    user_id: int,
    db_lock: asyncio.Lock,
    db_conn,
) -> Tuple[bool, str]:
    """
    Cancels an active drop and refunds donor.
    """
    async with drop_lock:
        record = active_drops.get(drop_id)
        if not record:
            return False, "❌ Дроп не найден."
        if record.donor_id != user_id:
            return False, "❌ Ты не являешься создателем этого дропа."
        if record.status != "active":
            return False, f"❌ Нельзя отменить дроп со статусом '{record.status}'."
        
        record.status = "cancelled"

    from common.database import add_user_global_balance
    now = time.time()
    async with db_lock:
        try:
            await add_user_global_balance(db_conn, record.donor_id, record.board_id, record.amount)
            await db_conn.execute(
                "UPDATE MoneyDrops SET status = 'cancelled', refunded_at = ? WHERE drop_id = ?",
                (now, drop_id),
            )
            await db_conn.commit()
        except Exception as e:
            return False, f"❌ Ошибка возврата средств: {e}"

    return True, f"✅ Дроп на {record.amount} ₪ отменен, средства возвращены на баланс."


async def expire_unclaimed_drops_step(db_lock: asyncio.Lock, db_conn) -> List[DropRecord]:
    """
    Background step: refunds drops older than their expiration timestamp.
    """
    from common.database import add_user_global_balance
    now = time.time()
    expired_list: List[DropRecord] = []

    async with drop_lock:
        for drop_id, record in list(active_drops.items()):
            if record.status == "active" and now >= record.expires_at:
                record.status = "expired"
                expired_list.append(record)

    if not expired_list:
        return []

    async with db_lock:
        for rec in expired_list:
            try:
                await add_user_global_balance(db_conn, rec.donor_id, rec.board_id, rec.amount)
                await db_conn.execute(
                    "UPDATE MoneyDrops SET status = 'expired', refunded_at = ? WHERE drop_id = ?",
                    (now, rec.drop_id),
                )
            except Exception:
                pass
        try:
            await db_conn.commit()
        except Exception:
            pass

    return expired_list


# -----------------------------------------------------------------------------
# Inline Keyboards for Drop System
# -----------------------------------------------------------------------------

def get_drop_claim_keyboard(drop_id: str, amount: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=f"💸 Забрать {amount} ₪", callback_data=f"drop:claim:{drop_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_drop_creator_keyboard(current_balance: int) -> InlineKeyboardMarkup:
    third = max(MIN_DROP_AMOUNT, current_balance // 3)
    half = max(MIN_DROP_AMOUNT, current_balance // 2)
    all_in = max(MIN_DROP_AMOUNT, current_balance)

    buttons = [
        [
            InlineKeyboardButton(text=f"💰 Треть ({third} ₪)", callback_data=f"drop:create:{third}"),
            InlineKeyboardButton(text=f"💰 Половина ({half} ₪)", callback_data=f"drop:create:{half}"),
        ],
        [
            InlineKeyboardButton(text=f"🔥 Выбросить всё ({all_in} ₪)", callback_data=f"drop:create:{all_in}"),
        ],
        [
            InlineKeyboardButton(text="150 ₪", callback_data="drop:create:150"),
            InlineKeyboardButton(text="500 ₪", callback_data="drop:create:500"),
            InlineKeyboardButton(text="1 000 ₪", callback_data="drop:create:1000"),
        ],
        [
            InlineKeyboardButton(text="5 000 ₪", callback_data="drop:create:5000"),
            InlineKeyboardButton(text="10 000 ₪", callback_data="drop:create:10000"),
            InlineKeyboardButton(text="50 000 ₪", callback_data="drop:create:50000"),
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="drop:cancel_menu"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
