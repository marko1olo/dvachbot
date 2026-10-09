from common.extractive_summary import (
    generate_extractive_summary,
    _parse_dump_lines,
    _extract_key_topics
)

def test_parse_dump_lines():
    sample = """
    Анон (Ответ на #100): Привет всем в этом треде! Обсуждаем видеокарты.
    [sticker]
    Мод: Посты со спамом будут удаляться немедленно.
    Юзер123: Nvidia выпустила новую 5090 за миллион рублей.
    """
    posts = _parse_dump_lines(sample)
    assert len(posts) == 3
    assert posts[0]["author"] == "Анон"
    assert posts[0]["reply_to"] == "100"
    assert "видеокарты" in posts[0]["text"]
    assert posts[1]["author"] == "Мод"
    assert posts[2]["author"] == "Юзер123"

def test_extract_key_topics():
    posts = [
        {"author": "A", "text": "Крипта и биткоин падают в цене."},
        {"author": "B", "text": "Биткоин снова обвалился, надо покупать крипту."},
        {"author": "C", "text": "Да крипта это вообще скам, биткоин рухнет до нуля."},
        {"author": "D", "text": "Согласен про биткоин, полный скам."}
    ]
    topics = _extract_key_topics(posts, max_topics=2)
    assert len(topics) > 0
    words = [t["keyword"].lower() for t in topics]
    assert "биткоин" in words or "крипта" in words

def test_generate_extractive_summary_empty_fallback():
    res = generate_extractive_summary("", prompt="сделай саммари")
    assert "Сводка палаты" in res or "активных обсуждений зафиксировано не было" in res

def test_generate_extractive_summary_standard_persona():
    sample = "\n".join([
        f"Анон_{i}: Обсуждение релиза нового ядра Linux и компилятора GCC версия {i}. Баги в кодовой базе критичны."
        for i in range(10)
    ])
    res = generate_extractive_summary(sample, prompt="Сделай краткую сводку треда")
    assert "СВОДКА ПАЛАТЫ" in res or "Саммари" in res
    assert "Главные темы" in res or "горячие обсуждения" in res
    assert "•" in res

def test_generate_extractive_summary_waha_persona():
    sample = "\n".join([
        f"Гвардеец_{i}: Еретики наступают на позиции СПО на планете Тарсис {i}. Защищаем святилище Омниссии!"
        for i in range(10)
    ])
    res = generate_extractive_summary(sample, prompt="Действуй в стиле вархаммер инквизиция")
    assert "ВОКС-ДОСЬЕ" in res or "инквизицион" in res.lower()
    assert "Омниссии" in res or "еретик" in res.lower()

def test_generate_extractive_summary_blat_persona():
    sample = "\n".join([
        f"Бродяга_{i}: В хате передел масти. Кто-то крысит пайку у смотрящего в камере номер {i}."
        for i in range(10)
    ])
    res = generate_extractive_summary(sample, prompt="Ты Кибер-Смотрящий, раскидай по понятиям")
    assert "Кибер-Смотрящ" in res or "хат" in res or "поняти" in res

def test_generate_extractive_summary_chat_mode():
    sample = "\n".join([
        f"User_{i}: Важное объявление для чата номер {i}: встречаемся в субботу."
        for i in range(10)
    ])
    res = generate_extractive_summary(sample, context_name="чат флудилка")
    assert "чат флудилка" in res

def test_generate_extractive_summary_html_safety():
    sample = "\n".join([
        f"Hacker_{i}: <script>alert({i})</script> & <b>жирный</b> <img src=x onerror=alert(1)>"
        for i in range(10)
    ])
    res = generate_extractive_summary(sample)
    assert "<script>" not in res
    assert "<img" not in res
