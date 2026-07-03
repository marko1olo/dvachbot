"""
polish_mode.py — Enterprise-grade Polish Mode transformation engine.
TRYB POLSKI 🇵🇱 Bóbr approved.
"""

import random
import re
from mode_visuals import create_visual_post

# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVATION / DEACTIVATION PHRASES
# ═══════════════════════════════════════════════════════════════════════════════

POLISH_PHRASES_START = [
    "🇵🇱 UWAGA, UWAGA! AKTYWOWANO TRYB POLSKI! 🇵🇱\n\nO, kurwa! Czas na pierogi, bigos i narzekanie na wszystko! POLSKA GUROM!",
    "O kurwa, jebany! Włączono 'Protokół Bóbr'! 🇵🇱 Czas rozkurwić system!",
    "BOSZE, CO ZA INBA! 🇵🇱 Wjeżdżamy z trybem polskim! Kto nie skacze, ten z PiS-u!",
    "Alarm! Poziom 'Polskości' w czacie przekroczył normę! WITAMY W POLSCE, KURWA!",
    "ROZPOCZYNAMY 'OPERACJĘ HUSARZ'! 🇵🇱 Skrzydła rozłożone, pierogi podgrzane. Do boju!",
    "Co jest, kurwa?! 🇵🇱 Tryb 'Janusz' aktywowany! Skarpetki do sandałów, siatka z Biedronki i jedziemy!",
    "No i chuj, no i cześć! Włączono tryb 'Polska Myśl Szkoleniowa'! Jakoś to będzie, kurwa!",
    "🇵🇱 BÓBR JEBANY! Tryb polski wjechał jak Passat TDI na autostradzie! Robert Kubica byłby dumny!",
    "JANUSZ MODE: ON 🇵🇱 Grill rozpalony, Żubrówka otwarta, Somsiad już patrzy zza płotu! POLSKA GUROM!",
    "🇵🇱 WIEDŹMIN by się nie powstydził! Tryb polski aktywny — wrzucamy bigos do Eurokolchozu!",
]

POLISH_PHRASES_END = [
    "Dobra, kurwa, wystarczy tego polskiego pierdolenia. 🇵🇱 Wracamy do normalności, bo zaraz nas PiS opodatkuje.",
    "Koniec inby. 🇵🇱 Bóbr poszedł spać. Tryb polski wyłączony, można znowu mówić po ludzku.",
    "Boże, jak mi wstyd... Wyłączamy ten tryb, zanim ktoś wezwie TVP Info.",
    "Wódka się skończyła, pierogi zjedzone. 🇵🇱 Polski cud gospodarczy dobiegł końca. Wyłączam tryb.",
    "Dobra, fajrant. Czas na przerwę od bycia Polakiem. To męczące, kurwa.",
    "Passat TDI zgasł, Maluch nie odpala. 🇵🇱 Koniec trybu polskiego. Somsiad może spać spokojnie.",
    "Grażyna zamknęła Biedronkę, Janusz schował sandały. 🇵🇱 Tryb polski — wyłączony. Nara!",
]

# ═══════════════════════════════════════════════════════════════════════════════
# TRANSFORMATION DATA
# ═══════════════════════════════════════════════════════════════════════════════

POLISH_DATA = {
    'prefixes': [
        "Słuchajcie, kurwa...",
        "Generalnie to jest tak:",
        "No więc, ja pierdolę,",
        "Patrzcie, co za akcja:",
        "Elo, mordeczko,",
        "No siema, byczku,",
        "Panie Kierowniku,",
        "Essa, ziomki,",
        "Janusz mówi tak:",
        "Bóbr jebany powiedział:",
        "Uwaga, bo Sebix gada:",
    ],
    'suffixes': [
        ", nie?",
        ", i chuj.",
        ", wiadomo.",
        ", tak to już jest.",
        ", masakra.",
        ", rozumiesz.",
        ". I tyle w temacie.",
        ", essa.",
        ". Polska Gurom.",
        ", mordeczko.",
        ", byczku.",
        ". Jak Bóg da.",
        ", no nie?",
        ". Pozdro z Biedronki.",
        ", takie życie w Polsce.",
    ],
    'injections': [
        "(ja pierdolę)",
        "(nosz kurwa)",
        "(co za żenada)",
        "(takie życie)",
        "(polska, rozumiesz)",
        "(bez kitu)",
        "(bóbr jebany)",
        "(o kurwa)",
        "(cholera jasna)",
        "(Janusz by się popłakał)",
        "(masakra)",
        "(no nie wierzę)",
        "(jak w Biedronce)",
        "(gówno, nie życie)",
        "(Grażyna, patrzaj)",
        "(Sebix potwierdza)",
        "(jak Wiedźmin powiedział)",
    ],
    'ending_swaps': [
        ", i chuj.",
        ", wiadomo.",
        ", kurwa mać.",
        ". Polska Gurom!",
        ", no nie?",
        ". Bóbr jebany.",
        ", mordeczko.",
        ". I tyle.",
        ", jak zawsze w tym kraju.",
    ],
    'replacements': {
        # ─── Приветствия и базовые слова ─────────────────────────────
        'привет': 'siema',
        'здравствуйте': 'dzień dobry',
        'здарова': 'elo',
        'здорово': 'elo',
        'пока': 'nara',
        'до свидания': 'do widzenia',
        'да': 'no',
        'нет': 'nie',
        'что': 'co',
        'хорошо': 'dobrze',
        'плохо': 'chujowo',
        'нормально': 'w porządku',
        'пожалуйста': 'proszę',
        'спасибо': 'dzięki',
        'большое спасибо': 'wielkie dzięki',
        'очень': 'bardzo',
        'конечно': 'pewnie',
        'отлично': 'zajebiście',
        'извини': 'sory',
        'извините': 'przepraszam',

        # ─── Люди: архетипы и персонажи ──────────────────────────────
        'друг': ['ziomek', 'mordeczko', 'byczku'],
        'друзья': 'ziomki',
        'враг': 'wróg',
        'женщина': ['kobieta', 'Grażyna', 'Karyna'],
        'мужчина': ['facet', 'Janusz', 'Sebix'],
        'мужик': ['Janusz', 'gościu', 'Sebix'],
        'парень': 'chłopak',
        'девушка': 'dziewczyna',
        'человек': 'gościu',
        'люди': 'ludzie',
        'семья': 'rodzina',
        'ребенок': 'dzieciak',
        'дети': 'dzieciaki',
        'сосед': 'Somsiad',
        'соседи': 'Somsiady',
        'начальник': 'Panie Kierowniku',
        'босс': 'Panie Kierowniku',
        'вор': 'złodziej',
        'воры': 'złodzieje',
        'немцы': 'Niemcy',
        'немец': 'Niemiec',

        # ─── Национальности ──────────────────────────────────────────
        'хохол': 'Ukrainiec',
        'россиянин': ['ruski', 'kacap'],
        'русня': ['ruski', 'kacap'],
        'пидорашка': ['ruski', 'kacap'],
        'русский': ['ruski', 'kacap'],
        'россия': ['Rosja', 'kacapstan'],
        'украинец': 'Ukrainiec',
        'поляк': 'Polak',
        'польша': 'Polska',
        'пидоран': ['ruski', 'kacap'],
        'руский': ['ruski', 'kacap'],

        # ─── Политика и общество ─────────────────────────────────────
        'президент': 'prezydent',
        'правительство': ['rząd', 'Eurokolchoz'],
        'полиция': 'policja',
        'армия': 'wojsko',
        'война': 'wojna',
        'европа': ['Europa', 'Eurokolchoz'],
        'евросоюз': 'Eurokolchoz',
        'выборы': 'wybory',
        'политика': 'polityka',
        'налог': 'podatek',
        'налоги': 'podatki',

        # ─── Вопросы и связки ────────────────────────────────────────
        'почему': 'dlaczego',
        'зачем': 'po co',
        'где': 'gdzie',
        'когда': 'kiedy',
        'как': 'jak',
        'кто': 'kto',
        'или': 'albo',
        'но': 'ale',
        'потому что': 'bo',
        'тому шо': 'bo',
        'поч': 'dlaczego',
        'ладно': 'dobra',
        'значит': 'znaczy',
        'может быть': 'może',
        'может': 'może',
        'наверное': 'pewnie',

        # ─── Ругательства и экспрессия ───────────────────────────────
        'пиздец': ['ja pierdolę', 'masakra', 'przejebane', 'o kurwa'],
        'сука': 'kurwa',
        'блять': 'kurwa mać',
        'блин': 'cholera',
        'черт': 'cholera',
        'нахой': 'chujowo',
        'заебись': 'zajebiście',
        'охуенно': 'zajebiście',
        'круто': ['zajebiście', 'ekstra'],
        'классно': 'zajebiście',
        'хуйня': 'chujnia',
        'хуево': 'chujowo',
        'нахуй': 'chujowo',
        'пидор': 'pedał',
        'говно': 'gówno',
        'жопа': 'dupa',
        'ебать': 'jebać',
        'мудак': 'chuj',
        'дерьмо': 'gówno',
        'отстой': ['gówno', 'masakra'],
        'ужас': ['masakra', 'ja pierdolę'],
        'кошмар': 'masakra',
        'капец': ['o kurwa', 'masakra'],
        'офигеть': ['o kurwa', 'ja pierdolę'],
        'ахуеть': ['o kurwa', 'ja pierdolę'],
        'ёбаный': 'jebany',
        'сволочь': 'skurwysyn',

        # ─── Бытовые понятия ─────────────────────────────────────────
        'дом': 'dom',
        'квартира': 'mieszkanie',
        'машина': ['samochód', 'Passat TDI', 'Maluch'],
        'работа': 'robota',
        'деньги': ['pieniądze', 'hajs'],
        'бабки': 'hajs',
        'зарплата': 'wypłata',
        'магазин': ['sklep', 'Biedronka'],
        'школа': 'szkoła',
        'университет': 'studia',
        'тачка': ['samochód', 'Passat TDI', 'Maluch'],
        'шарага': 'studia',
        'авто': ['samochód', 'Passat TDI'],
        'шкила': 'szkoła',
        'уник': 'studia',

        # ─── Еда и напитки (Pierogi, Bigos, Kiełbasa...) ────────────
        'еда': ['jedzenie', 'pierogi', 'bigos'],
        'вода': 'woda',
        'пиво': 'piwo',
        'водка': ['wódka', 'Żubrówka'],
        'колбаса': 'kiełbasa',
        'сосиска': 'kiełbasa',
        'пельмени': 'pierogi',
        'вареники': 'pierogi',
        'суп': 'żurek',
        'борщ': 'barszcz',
        'обед': 'obiad',
        'завтрак': 'śniadanie',
        'ужин': 'kolacja',
        'мясо': 'mięso',
        'хлеб': 'chleb',
        'сыр': 'ser',

        # ─── Транспорт ───────────────────────────────────────────────
        'автобус': 'autobus',
        'поезд': 'pociąg',
        'самолет': 'samolot',
        'велосипед': 'rower',
        'такси': 'taxi',
        'метро': 'metro',
        'бензин': 'benzyna',
        'дорога': 'droga',

        # ─── Пляж и отдых (Parawan!) ────────────────────────────────
        'пляж': 'plaża z parawanem',
        'море': 'morze',
        'отдых': 'urlop',
        'отпуск': 'urlop',
        'зонт': 'parawan',

        # ─── Интернет и сленг ────────────────────────────────────────
        'лол': 'xD',
        'кек': 'beka',
        'кринж': 'cringe',
        'жиза': 'życiowe',
        'база': 'baza',
        'рофл': 'beka',
        'лмао': 'xDDD',
        'игра': 'gra',
        'игрок': 'gracz',
        'компьютер': 'komputer',
        'телефон': 'telefon',
        'интернет': 'internet',
        'чат': 'czat',
        'сообщение': 'wiadomość',
        'админ': 'admin',
        'тгач': 'czat',
        'двач': 'czat',

        # ─── Эмоции и состояния ──────────────────────────────────────
        'счастье': 'szczęście',
        'грусть': 'smutek',
        'злость': 'wkurw',
        'злой': 'wkurwiony',
        'устал': 'zmęczony',
        'скучно': 'nudno',
        'весело': 'wesoło',
        'смешно': 'śmieszne',
        'страшно': 'straszne',
        'красиво': 'ładne',
        'ужасно': 'okropne',
        'любовь': 'miłość',
        'ненависть': 'nienawiść',

        # ─── Мемы и культура ─────────────────────────────────────────
        'бобр': 'Bóbr jebany',
        'ведьмак': 'Wiedźmin',
        'гонщик': 'Robert Kubica',
        'папа': ['Jan Paweł II', 'tata'],
        'легенда': ['Polska Gurom', 'Robert Kubica'],
        'герой': 'husarz',
        'победа': 'zwycięstwo, Polska Gurom!',
        'проиграл': 'przegrał jak nie Kubica',

        'пукнул': ['pierdnął', 'puścił bąka'],
        'пукать': ['pierdzieć', 'sadzić bąki'],
        'анальный':['analny', 'w dupę'],
        'пробка': ['korek w dupie', 'zatyczka'],
        'баребухи': ['gówna', 'bobki'],
        'сушить': 'suszyć',
        'аутист': ['autysta', 'debil', 'pojeb'],
        'хлороформ':['chloroform', 'wóda usypiająca'],
        'тайга': ['las', 'Podlasie', 'zadupie'],
        'заложник': 'zakładnik',
        'заложники': 'zakładnicy',
        'одиночество': ['samotność', 'brak wódki'],
        'триада': 'triada',
        'кончил': ['spuścił się', 'skończył'],
        'кончила': 'spuściła się',
        'кончили': 'spuścili się',
        'сперма':['sperma', 'spust', 'białe szaleństwo'],
        'такса':['jamnik', 'krzywy pies'],
        'огурец': ['ogórek kiszony', 'ogóras'],
        'сандалии': ['sandały z białymi skarpetami', 'sandały Janusza'],
        'рекламил': ['reklamował', 'wciskał kit'],
        'очкошник':['tchórz', 'pizda', 'cykor'],
        'очкошников': ['tchórzy', 'pizd'],
        'параша': ['kibel', 'gówno', 'chujnia'],
        'съебутся': ['spierdolą', 'uciekną'],
        'сьебутся':['spierdolą', 'uciekną'],
        'съебался': ['spierdolił', 'uciekł'],
        'сьебался': ['spierdolił', 'uciekł'],
        'крестный ход':['procesja', 'marsz katoli'],
        'обществознание':['WOS', 'pierdolenie o państwie'],
        'двощи': ['wykop', 'czan', 'śmietnik'],
        'тытруба': 'jutub',
        'видосик': ['filmik', 'wideo'],
        'голова': ['łeb', 'makówka', 'baniak'],
        'мозг':['mózg', 'rozum'],
        'пасха': ['Wielkanoc', 'święta'],
        'иисус':['Jezus', 'Bozia'],
        'куличи': ['babki wielkanocne', 'ciasta'],
        'кулич': 'babka wielkanocna',
        'совок':['komuna', 'PRL', 'ruska bieda'],
        'ссср': ['ZSRR', 'ruska komuna'],
        'хрущевка':['blok z wielkiej płyty', 'klitka'],
        'хрущевки': ['bloki z płyty', 'klitki'],
        'космос': 'kosmos',
        'донатер':['sponsor', 'naiwniak z hajsem', 'bankomat'],
        'кроссовки': ['adidasy', 'najki', 'cichobiegi'],
        'трусы': ['gacie', 'majty', 'gacie z drachą'],
        'качалка': ['siłka', 'siłownia'],
        'микроволновка':['mikrofalówka', 'mikrofala'],
        'холодильник': ['lodówka', 'chłodziarka'],
        'насрал':['nasrał', 'najebał kloca', 'zjebał się'],
        'пернул': ['pierdnął', 'puścił bąka', 'zjebał się'],
        'подрочил':['zwalił konia', 'rzepę trzepał', 'marszczył freda'],
        'жирный':['grubas', 'świnia', 'tłusty knur'],
        'лысый': ['łysy chuj', 'łysa pała'],
        'курьер':['dostawca z UberEats', 'kurier z paczką'],
        'завод':['kołchoz', 'fabryka smrodu', 'zakład', 'obóz pracy'],
        'ипотека':['kredyt we frankach', 'kredyt na 30 lat', 'chujnia z bankiem', 'pętla na szyi'],
        'кредит':['chwilówka', 'kredyt u żyda', 'długi'],
        'бухать':['chlać', 'łoić wódę', 'pić jak świnia', 'najebać się'],
        'ныть':['pierdolić smuty', 'marudzić jak baba', 'płakać', 'narzekać jak prawdziwy Polak'],
        'троллить':['kręcić bekę', 'odkurwiać inbę', 'robić w chuja', 'kręcić gównoburzę'],
        'слился':['obsrał zbroję', 'spierdolił', 'poddał się', 'uciekł jak cwel'],
        'оправдываться':['tłumaczyć się jak cwel', 'szukać wymówek'],
        'байтить':['prowokować', 'szukać dymu', 'robić podchody'],
        'шаурма':['kebab', 'kebab na cienkim', 'kebab u Turka', 'kapsalon'],
        'пельмени':['pierogi', 'pierogi z mięsem', 'uszka'],
        'омега':['przegryw', 'stuleja', 'cwel', 'pizda'],
        'альфа':['Oskarek', 'kozak', 'szef', 'byczek'],
        'нормис':['normik', 'zwykły Polak', 'Janusz', 'zwyklak'],
        'чмо':['śmieć', 'zjeb', 'chuj', 'kurwi syn'],
        'пиздабол':['kłamca', 'bajerant', 'pierdolnik', 'farmazon'],
        'деанон':['dojazd', 'wystalkowanie', 'ujebanie w necie'],
        'подпивас':['Janusz z Harnasiem', 'piwosz', 'grubas z piwem', 'wujek Staszek'],
        'аноним': ['anon', 'ktos', 'ukryty'],
        'анонимус': ['anonimus', 'haker'],
        'анонимы': ['anonimy', 'ludzie z netu'],
        'анонимов': ['anonimów', 'ludzi'],
        'битард': ['piwniczak', 'no-life', 'stulejarz'],
        'битарды': ['piwniczaki', 'no-life’y'],
        'мусор': ['śmieci', 'odpady'],
        'мусора': ['psy', 'gliny', 'niebiescy'],
        'мусоров': ['psów', 'gliniarzy'],
        'мусорской': ['psi', 'policyjny'],
        'кукарекать': ['szczekać', 'pierdolić głupoty', 'miauczeć'],
        'кукарекаешь': ['szczekasz', 'pierdolisz'],
        'кукарекает': ['szczeka', 'pierdoli'],
        'годный': ['fajny', 'git', 'dobry'],
        'годная': ['fajna', 'dobra', 'git'],
        'годное': ['fajne', 'dobre'],
        'годнота': ['fajne gówno', 'złoto'],
        'подмыться': ['umyć dupę', 'podmyć się'],
        'подмылся': ['umył dupę', 'podmył się'],
        'вебка': ['kamerka', 'oko'],
        'вебку': ['kamerkę'],
        'галера': ['kołchoz', 'robota u żyda'],
        'галере': ['kołchozie', 'robocie'],
        'золото': ['złoto', 'hajs'],
        'золотой': ['złoty', 'bogaty'],
        'сажа': ['sadza', 'brud'],
        'сажей': ['sadzą', 'brudem'],
        'вайп': ['czystka', 'usuwanie'],
        'вайпать': ['czyścić', 'usuwać'],
        'анонимом': ['anonem', 'ukrytym'],
        'анониму': ['anonowi'],
        'битарда': ['piwniczaka', 'stulejarza'],
        'битарду': ['stulejarzowi', 'przegrywowi'],
        'битардом': ['piwniczakiem'],
        'тянку': ['loszkę', 'dupeczkę', 'dziewczynę'],
        'тянке': ['loszce', 'dziewczynie'],
        'тянкой': ['dupeczką', 'loszką'],
        'инцела': ['incela', 'przegrywa'],
        'инцелу': ['incelowi'],
        'куколда': ['cuckolda', 'rogacza'],
        'куколду': ['rogaczowi'],
        'бати': ['ojca', 'starego'],
        'бате': ['ojcu', 'staremu'],
        'батей': ['ojcem', 'starym'],
        'заводом': ['kołchozem', 'zakładem'],
        'заводе': ['kołchozie', 'zakładzie'],
        'падика': ['klatki', 'blokowiska'],
        'падике': ['klatce', 'pod blokiem'],
        'спермой': ['spustem', 'spermą'],
        'попе': ['dupie', 'rzyci'],
        'попу': ['dupę'],
        'попой': ['dupą'],
        'бухает': ['chleje', 'pije', 'wali wódę'],
        'бухаешь': ['chlejesz', 'walisz'],
        'бухают': ['chlają', 'piją'],
        'слился': ['obsrał się', 'uciekł', 'pękł'],
        'слилась': ['obsrała się', 'uciekła'],
        'слились': ['obsrali się'],
        'пиздишь': ['kłamiesz', 'pierdolisz głupoty'],
        'пиздит': ['pierdoli', 'kłamie'],
        'кукарекают': ['szczekają', 'pierdolą'],
        'пузо': ['brzuch', 'bebech', 'mięsień piwny'],
        'пуза': ['brzucha', 'bebecha'],
        'живот': ['brzuch', 'podbrzusze'],
        'ноги': ['nogi', 'szłapy', 'syry'],
        'ногами': ['nogami', 'szłapami'],
        'руки': ['ręce', 'łapy', 'grabie'],
        'руками': ['rękami', 'łapami'],
        'глаза': ['oczy', 'gały', 'ślepia'],
        'глаз': ['oczu', 'gałów'],
        'глазами': ['oczami', 'gałami'],
        'уши': ['uszy', 'uchole'],
        'жрать': ['żreć', 'opierdalać', 'żreć kurwa'],
        'жрешь': ['żresz', 'jadasz'],
        'жрет': ['żre', 'wpierdala'],
        'жрут': ['żrą', 'wpierdalają'],
        'бухали': ['chlali', 'pili', 'walili wódę'],
        'ссылка': ['link', 'odnośnik'],
        'ссылку': ['linka'],
        'ссылки': ['linki'],
        'сайт': ['strona', 'witryna', 'portal'],
        'сайта': ['strony'],
        'коммент': ['komentarz', 'wpis'],
        'комменты': ['komentarze'],
        'пруф': ['dowód', 'proof', 'potwierdzenie'],
        'пруфы': ['dowody', 'screeny'],
        'пруфов': ['dowodów'],
        'сижу': ['siedzę', 'gniję', 'czatuję'],
        'сидишь': ['siedzisz', 'gnijesz'],
        'сидят': ['siedzą', 'gniją'],
        'пишу': ['piszę', 'bazgram', 'skrobię'],
        'пишешь': ['piszesz', 'skrobiesz'],
        'пишут': ['piszą', 'bazgrają'],
        'слушаю': ['słucham', 'podsłuchuję'],
        'слушаешь': ['słuchasz'],
        'слушают': ['słuchają'],
        'горит': ['pali się', 'jara się', 'płonie'],
        'горят': ['palą się', 'jarają się'],
        'взрывается': ['wybucha', 'rozpierdala się'],
        'взорвали': ['rozjebali', 'wysadzili w powietrze'],
        'бахнуло': ['jebnęło', 'walnęło'],
        'удалил': ['usunął', 'wywalił', 'skasował'],
        'удалили': ['usunęli', 'wywalili'],
        'спамит': ['spamuje', 'sra postami'],
        'воняет': ['śmierdzi', 'jedzie'],
        'пахнет': ['pachnie', 'pachnie jak'],
        'устал': ['zmęczyłem się', 'ujebałem się'],
        'устали': ['zmęczyli się', 'ujebali się'],
        'смешно': ['śmiesznie', 'bekowo'],
        'страшно': ['strasznie', 'strach się bać'],
        'удалено': ['usunięte', 'wywalone'],
        'часто': ['często', 'co chwila', 'non stop'],
        'редко': ['rzadko', 'od święta'],
        'быстро': ['szybko', 'migiem', 'raz-dwa'],
        'медленно': ['powoli', 'wolno', 'jak żółw'],
        'ноутбук': ['laptop', 'komp'],
        'зарядка': ['ładowarka'],
        'свет': ['światło', 'prąd'],
        'темнота': ['ciemność', 'mrok'],
        'ложь': ['kłamstwo', 'ściema', 'pierdolenie'],
        'лживый': ['kłamliwy', 'fałszywy'],
        'лживая': ['kłamliwa', 'fałszywa'],
        'врешь': ['kłamiesz', 'ściemniasz', 'pierdolisz'],
        'врет': ['kłamie', 'pierdoli'],
        'врут': ['kłamią', 'pierdolą głupoty'],
        'правду': ['prawdę', 'serio'],
        'много': ['dużo', 'od groma', 'w opór', 'dużo kurwa'],
        'мало': ['mało', 'trochę', 'tyle co nic'],
        'ничего': ['nic', 'nullo'],
        'все': ['wszyscy', 'cała inba'],
        'всем': ['wszystkim'],
        'сейчас': ['teraz', 'już', 'zaraz'],
        'больница': ['szpital', 'umieralnia'],
        'больнице': ['szpitalu'],
        'больницу': ['szpitala'],
        'врач': ['lekarz', 'konował'],
        'врача': ['lekarza', 'specjalisty'],
        'аптека': ['apteka'],
        'таблетки': ['pigułki', 'leki', 'tabsy'],
        'таблетками': ['lekami'],
        'болею': ['choruję', 'zdycham'],
        'болеешь': ['chorujesz'],
        'болеет': ['choruje'],
        'лекарство': ['lek', 'lekarstwo'],
        'машину': ['auto', 'passata', 'brykę'],
        'машины': ['samochody', 'auta'],
        'машиной': ['autem', 'wozem'],
        'автобус': ['autobus', 'zbiorkom'],
        'автобусе': ['autobusie'],
        'такси': ['taryfa', 'taxi'],
        'дорога': ['droga', 'trasa'],
        'дороге': ['drodze'],
        'приехал': ['przyjechał', 'wbił'],
        'уехал': ['wyjechał', 'spierdolił'],
        'еду': ['jadę'],
        'едешь': ['jedziesz'],
        'батарейка': ['bateria', 'akumulator'],
        'экран': ['ekran', 'monitor'],
        'экране': ['ekranie'],
        'клавиатура': ['klawiatura', 'klawa'],
        'клавиатуре': ['klawiaturze'],
        'мышка': ['myszka'],
        'кнопка': ['przycisk', 'guzik'],
        'кнопку': ['przycisk'],
        'лагает': ['laguje', 'muli', 'tnie się'],
        'лагают': ['lagują'],
        'сломался': ['rozjebał się', 'padł', 'zepsuł się'],
        'сломалась': ['rozjebała się'],
        'чинить': ['naprawiać', 'reanimować'],
        'скучно': ['nuda', 'nudno jak w kościele'],
        'тупой': ['tępy', 'głupi', 'debilny'],
        'тупая': ['głupia', 'tępa'],
        'тупые': ['tępe chuje', 'debile'],
        'гений': ['geniusz', 'szef', 'mózg'],
        'ждем': ['czekamy'],
        'удаляешь': ['usuwasz', 'wywalasz'],
        'удаляет': ['usuwa', 'kasuje'],
        'свидание': ['randka', 'spotkanie z loszką'],
        'свидании': ['randce'],
        'отношения': ['związek', 'relacja'],
        'отношениях': ['związku'],
        'подкатывать': ['podrywać', 'bajerować', 'startować do niej'],
        'подкатил': ['podbił', 'zagadał'],
        'сосаться': ['lizać się', 'cmokać się'],
        'сосались': ['lizali się'],
        'изменяет': ['zdradza', 'skacze w bok'],
        'изменила': ['przyprawiła rogi', 'zdradziła'],
        'ревнует': ['jest zazdrosny', 'robi inbę'],
        'бросил': ['rzucił', 'olał', 'pogonił'],
        'бросила': ['rzuciła', 'zostawiła'],
        'влюбился': ['zakochał się', 'poleciał na nią'],
        'шлюха': ['szmata', 'dziwka', 'blachara', 'pukawka'],
        'шлюхой': ['szmatą'],
        'шлюхи': ['szmaty', 'kurwy'],
        'девственница': ['dziewica', 'cnotka'],
        'куколдят': ['robią z niego rogacza'],
        'альфачу': ['Oskarkowi', 'szefowi'],
        'альфачом': ['byczkiem'],
        'инцелов': ['stulejarzy', 'przegrywów'],
        'американцы':['Amerykanie', 'jankesi'],
        'американец': ['Amerykanin', 'jankes'],
        'нейрослоп': ['gówno z AI', 'sztuczna inteligencja'],
        'бутылка':['butelka', 'flaszka wódki'],
        'бутылку':['butelkę', 'flaszkę wódki'],
        'пялиться':['gapić się', 'wlepiać gały'],
        'пялюсь': 'gapię się',
        'пялится': 'gapi się',
        'кальянщица': 'laska od sziszy',
        'антидепрессанты': ['antydepresanty', 'wóda z lekami'],
        'наркота': ['narkotyki', 'mefedron', 'ćpanie'],
        'наркоманство': ['ćpanie', 'narkomania'],
        'блевать':['rzygać', 'haftować'],
        'авианосец': 'lotniskowiec',
        'сгорела': 'spaliła się w pizdu',
        'сгорел': 'spalił się w pizdu',
        'понос': ['sraczka', 'biegunka'],
        'диарея': ['sraczka', 'biegunka'],
        'кал': ['kał', 'gówno'],
        'босота': ['patologia', 'dresy', 'biedota'],
        'пукан': ['dupa', 'rzyć', 'odbyt'],
        'сглазил': 'zauroczył',
        'сглазили': 'zauroczyli',
        'чердак': 'strych',
        'возгорание': ['pożar', 'ogień'],
        'пролив': 'cieśnina',
        'порт': 'port',
        'импорт': 'import',
        'измором': 'głodem',
        'надельку': 'na tydzień',
        'тихонечко': 'cichutko',
        'целиком': 'całkowicie',
        'супер':['super', 'zajebiście'],
        'падик': ['klatka schodowa', 'klatka'],
        'дверь': 'drzwi',
        'выпадает': 'wypada',
        'прошу': 'proszę',
        'чушпан':['frajer', 'łeb', 'ciota'],
        'еотова':['szmula', 'loszka'],
        'сыч': ['piwniczak', 'przegryw'],
        'ерохин': ['Oskarek', 'Chad'],
        'алко':['wóda', 'alko', 'chlanie'],
        'комбикорм': ['pasza', 'żarcie dla świń'],
        'вагину': ['cipę', 'pizdę'],
        'слюни': 'ślina',
        'инцел': ['przegryw', 'incel'],
        'накачать':['upić', 'naćpać'],
        'держать': ['trzymać', 'kisić'],
        'нежен': ['delikatny', 'miękki'],
        'доброжелателен': 'miły',
        'заменили': 'zamienili',
        'дали': 'dali',
        'гордиться': ['być dumnym', 'chwalić się'],
        'хуже':['gorzej', 'chujowiej'],
        'запретили': ['zabronili', 'zakazali'],
        'шествия': ['marsze', 'parady'],
        'воскресению': 'zmartwychwstaniu',
        'русских': ['kacapów', 'ruskich'],
        'лиц':['mord', 'ryjów'],
        'традицию': 'tradycję',
        'скрепы':['polskie tradycje', 'cebulactwo'],
        'исламистам': 'ciapatym',
        'рамадан': 'ramadan',
        'мгу': 'uniwerek w Moskwie',
        'фашизма': 'faszyzmu',
        'сатанизм': 'satanizm',
        'западу': 'Zachodowi',
        'терпению': 'cierpliwości',
        'сидеть': 'siedzieć',
        'школе': 'budzie',
        'писать': 'pisać',
        'контрольную': ['sprawdzian', 'kartkówkę'],
        'динамиков': 'głośników',
        'закипать': ['gotować się', 'wkurwiać się'],
        'кровь': 'krew',
        'стенкам': 'ścianom',
        'размазывает': 'rozsmarowuje',
        'фанатизм': 'fanatyzm',
        'серых': 'szarych',
        'сынчела':['synek', 'gówniak', 'bąbelek'],
        'ублюдок':['skurwiel', 'chuj'],
        'завали': ['zamknij mordę', 'stul pysk'],
        'хряк': ['knur', 'wieprz'],
        'поебывать':['pukać', 'ruchać', 'bolcować'],
        'сестру': 'siostrę',
        'поставлю': 'postawię',
        'торчит': 'sterczy',
        'пиздака': 'pizdy',
        'летающий': 'latający',
        'аппарат': 'aparat',
        'пятиклассника': 'gówniaka z piątej klasy',
        'ломает': 'łamie',
        'воровала': ['kradła', 'zapierdalała'],
        'спалил': 'spalił',
        'гниль': 'zgnilizna',
        'предатель':['zdrajca', 'konfident', 'kapuś'],
        'маньяку': ['zboczeńcowi', 'psycholowi'],
        'расстрелять': 'rozstrzelać',
        'забила':['olała', 'wyjebała na to'],
        'уголовное': 'karne',
        'дело': 'sprawę',
        'оскорбления': ['obrazy', 'wyzwiska'],
        'чувств': 'uczuć',
        'верующих': ['wierzących', 'katoli'],
        'колонии': ['więzienia', 'pudła'],
        'поздняков': 'Pozdniakow (ruski cwel)',
        'отвратительной': 'ohydnej',
        'бумага':['papier', 'srajtaśma'],
        'горит': ['pali się', 'fajczy się'],
        'стоимость': 'cena',
        'вошел': ['wszedł', 'wbił'],
        'залив': 'zatokę',
        'блокаду': 'blokadę',
        'пролива': 'cieśniny',
        'выписан': ['wyjebany', 'skreślony'],
        'комарово': 'Komarowo (jakieś zadupie)',
        'москва':['Moskwa', 'kacapskie miasto'],
        'ребятки':['mordeczki', 'chłopaki'],
        'очко': ['oko', 'dupa', 'rów'],
        'анус':['odbyt', 'sraka'],
        'пердак': ['tyłek', 'dupsko'],
        'пленник': 'jeniec',
        'депрессия': ['depresja', 'smuty', 'brak wódki'],
        'спамил': ['spamił', 'srał postami'],
        'форсил': 'wciskał',
        'дно': ['dno', 'gówno'],
        'россии':['Rosji', 'kacapstanu'],
        'россию': ['Rosję', 'kacapstan'],
        'власть': ['władza', 'rządzący', 'politycy'],
        'митинг':['protest', 'strajk', 'inba na ulicy'],
        'молитва': 'modlitwa do Bozi',
        'угроза': 'groźba',
        'препод':['wykładowca', 'profesorek', 'nauczyciel'],
        'слезы': 'łzy',
        'любовь': 'miłość',
        'милосердие': 'litość',
        'бомжи':['żule', 'menele', 'bezdomni'],
        'полет': 'lot',
        'нейросеть': 'sztuczna inteligencja',
        'шмотки': ['ciuchy', 'łachy'],
        'шпион': ['szpieg', 'kret'],
        'иноагент': 'obcy agent',
        'убийца': 'morderca',
        'суд': 'sąd',
        'тюрьма': ['więzienie', 'puszka', 'kryminał'],
        'онлифанс':['OnlyFans', 'stronka dla kurew'],
        'вебкам': 'kamerki',
        'хавка': ['żarcie', 'szama'],
        'тошнит': 'rzygać się chce',
        'рвота': ['rzygi', 'paw'],
        'апартаменты': 'apartamenty',
        'огонь': 'ogień',
        'байден': 'Biden',
        'экономика': 'gospodarka',
        'санкции': 'sankcje',
        'сон': 'sen',
        'приснился': 'przyśnił się',
        'игры': 'gry',
        'комп':['komp', 'pecet'],
        'мамка': ['stara', 'matka', 'matula'],
        'конча':['spust', 'sperma'],
        'малафья': 'sperma',
        'бан': 'ban',
        'забанили': ['zbanowali', 'wyjebali'],
        'модератор':['jany mod', 'admin', 'cieć'],
        'модер': 'mod',
        'школьник': ['gimbus', 'szkolniak'],
        'школота':['gimbaza', 'dzieciarnia'],
        'мем': ['mem', 'śmieszek'],
        'мемы':['memy', 'śmieszki'],
        'фотка': ['fota', 'zdjątko'],
        'телефон':['telefon', 'komórka'],
        'мобила': ['komórka', 'fon'],
        'срач':['gównoburza', 'inba', 'kłótnia'],
        'лицо':['morda', 'ryj', 'twarz'],
        'туалет': ['kibel', 'sracz', 'kibelek'],
        'сортир': ['sracz', 'kibel'],
        'мыться': 'myć się',
        'душ': 'prysznic',
        'жена': ['żona', 'stara', 'Grażyna'],
        'муж':['mąż', 'stary', 'Janusz'],
        'измена': ['zdrada', 'skok w bok'],
        'развод': 'rozwód',
        'девственник': ['prawiczek', 'przegryw'],
        'налоги': ['podatki', 'złodziejstwo rządu'],
        'зарплата':['wypłata', 'hajs'],
        'пенсия': ['emerytura', 'głodowe ochłapy'],
        'телевизор': ['telewizor', 'pudło'],
        'мент':['pies', 'glina', 'krawężnik'],
        'менты': ['psy', 'gliny'],
        'полиция':['policja', 'psy'],
        'пиво': ['piwo', 'browar', 'piwko'],
        'плакать': ['ryczeć', 'płakać'],
        'боль': 'ból',
        'смех': 'śmiech',
        'смеяться': 'śmiać się',

    }
}

# ═══════════════════════════════════════════════════════════════════════════════
# COMPILED REGEX ENGINE (performance-critical)
# ═══════════════════════════════════════════════════════════════════════════════

_sorted_keys = sorted(POLISH_DATA['replacements'].keys(), key=len, reverse=True)
_REPLACEMENT_PATTERN = re.compile(
    r'(?<!\w)(' + '|'.join(re.escape(k) for k in _sorted_keys) + r')(?!\w)',
    flags=re.IGNORECASE
)
_COMMA_PATTERN = re.compile(r',')
_ENDING_DOT_PATTERN = re.compile(r'\.\s*$')
_ADJ_YY_PATTERN = re.compile(r'ый$')
_ADJ_IY_PATTERN = re.compile(r'ий$')
_ADJ_OV_PATTERN = re.compile(r'ов$')
_ADJ_EV_PATTERN = re.compile(r'ев$')
_POLONIZE_WORD_PATTERN = re.compile(r'\b[А-Яа-яЁёA-Za-z]{4,}\b')


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE STAGES
# ═══════════════════════════════════════════════════════════════════════════════

def _case_aware_replace(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original and original[0].isupper():
        return replacement[0].upper() + replacement[1:] if len(replacement) > 1 else replacement.upper()
    return replacement


def _stage_word_replacement(text: str) -> str:
    def _replacer(match: re.Match) -> str:
        original = match.group(0)
        key = original.lower()
        value = POLISH_DATA['replacements'].get(key)
        if value is None:
            return original
        if isinstance(value, list):
            chosen = random.choice(value)
        else:
            chosen = value
        return _case_aware_replace(original, chosen)

    return _REPLACEMENT_PATTERN.sub(_replacer, text)


def _stage_kurwa_comma(text: str) -> str:
    def _comma_replacer(match: re.Match) -> str:
        return ", kurwa," if random.random() < 0.4 else ","
    return _COMMA_PATTERN.sub(_comma_replacer, text)


def _stage_ending_transform(text: str) -> str:
    if _ENDING_DOT_PATTERN.search(text) and random.random() < 0.30:
        chosen = random.choice(POLISH_DATA['ending_swaps'])
        text = _ENDING_DOT_PATTERN.sub(chosen, text)
    return text


def _stage_prefix(text: str) -> str:
    if random.random() < 0.35:
        return f"{random.choice(POLISH_DATA['prefixes'])} {text}"
    return text


def _stage_suffix(text: str) -> str:
    if random.random() < 0.55:
        if text.endswith('.'):
            text = text[:-1]
        return f"{text}{random.choice(POLISH_DATA['suffixes'])}"
    return text


def _stage_injection(text: str, word_count: int) -> str:
    if word_count > 5 and random.random() < 0.25:
        words = text.split()
        if len(words) > 2:
            point = random.randint(1, len(words) - 1)
            words.insert(point, random.choice(POLISH_DATA['injections']))
            return ' '.join(words)
    return text

def _stage_pseudo_polish(text: str) -> str:
    if random.random() > 0.4:
        return text

    def _polonize(m):
        word = m.group(0)
        if word.isupper():
            return word
        # Визуальная полонизация
        w = word.replace('ш', 'sz').replace('ч', 'čz').replace('ц', 'č').replace('в', 'w')
        w = w.replace('Ш', 'Sz').replace('Ч', 'Čz').replace('Ц', 'Č').replace('В', 'W')
        # Замена окончаний прилагательных
        w = _ADJ_YY_PATTERN.sub('ỹ', w)
        w = _ADJ_IY_PATTERN.sub('i', w)
        w = _ADJ_OV_PATTERN.sub('ów', w)
        w = _ADJ_EV_PATTERN.sub('ów', w)
        return w

    # Применяем только к словам длиннее 3 символов, чтобы не сломать предлоги (в, с)
    return _POLONIZE_WORD_PATTERN.sub(_polonize, text)
# ═══════════════════════════════════════════════════════════════════════════════
# MAIN TRANSFORM FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

def polish_transform(text: str, header: str | None = None) -> tuple[str, str | bytes]:
    """
    Enterprise-grade Polish transformation pipeline.

    Returns:
        ('image', bytes) — if visual post was generated
        ('text', str)    — transformed text
    """
    if not text:
        return ('text', "")

    # ── Pipeline Stage 1: Word replacement ───────────────────────────
    result = _stage_word_replacement(text)

    word_count = len(result.split())

    # Short messages get minimal treatment
    if word_count <= 2:
        if random.random() < 0.4:
            result += ", kurwa"
        # Visual chance for short messages too
        if len(text) < 180 and random.random() < 0.25:
            image_bytes = create_visual_post('polish', result, header)
            if image_bytes:
                return ('image', image_bytes)
        return ('text', result)

    # ── Pipeline Stage 2: Kurwa-comma injection ──────────────────────
    result = _stage_kurwa_comma(result)

    # ── Pipeline Stage 3: Ending dot transformation ──────────────────
    result = _stage_ending_transform(result)

    # ── Pipeline Stage 4: Prefix ─────────────────────────────────────
    result = _stage_prefix(result)

    # ── Pipeline Stage 5: Suffix ─────────────────────────────────────
    result = _stage_suffix(result)

    # ── Pipeline Stage 6: Mid-sentence injection ─────────────────────
    result = _stage_injection(result, word_count)

    # ── Pipeline Stage 7: Pseudo-Polish Orthography ──────────────────
    result = _stage_pseudo_polish(result)
    
    # ── Visual generation chance ─────────────────────────────────────
    if len(text) < 180 and random.random() < 0.25:
        image_bytes = create_visual_post('polish', result, header)
        if image_bytes:
            return ('image', image_bytes)

    return ('text', result)