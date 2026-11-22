import pytest
import time
from common.spam_filter import check_link_or_ad_spam, check_text_copro_flood
from main import RAID_LOCKDOWN_THRESHOLD
from combat_moderation_engine import _TARGET_PAIR_LAST_ATTACK, record_combat_attack, save_combat_cooldowns

def test_spam_filter_immunity_removed():
    # User with > 50 posts should NOT have immunity for scam/invite links anymore
    user_id = 12345
    posts_count = 100
    
    # Scam text
    is_spam, reason = check_link_or_ad_spam(user_id, "b", "1xbet", posts_count=posts_count)
    assert is_spam is True, "Scam should be detected even for user with > 50 posts"
    
    # Invite link
    is_spam, reason = check_link_or_ad_spam(user_id, "b", "t.me/+invite_link", posts_count=posts_count)
    assert is_spam is True, "Invite link should be detected even for user with > 50 posts"

def test_copro_flood_threshold():
    # 4 roots should NOT trigger now (threshold raised to 5)
    text = "калл говно дрист срак" # 4 roots
    is_flood, reason = check_text_copro_flood(text)
    assert is_flood is False, "4 roots should NOT trigger copro flood"
    
    # 5 roots SHOULD trigger
    text = "калл говно дрист срак говнон"
    is_flood, reason = check_text_copro_flood(text)
    assert is_flood is True, "5 roots SHOULD trigger copro flood"

def test_raid_lockdown_threshold():
    assert RAID_LOCKDOWN_THRESHOLD == 12, "Raid lockdown threshold should be 12"

def test_combat_persistency():
    # Clear and set attack
    _TARGET_PAIR_LAST_ATTACK.clear()
    record_combat_attack(1, 2, 'partyvan')
    assert (1, 2) in _TARGET_PAIR_LAST_ATTACK
    
    # Simulate restart by clearing memory and loading
    _TARGET_PAIR_LAST_ATTACK.clear()
    from combat_moderation_engine import load_combat_cooldowns
    load_combat_cooldowns()
    assert (1, 2) in _TARGET_PAIR_LAST_ATTACK, "Cooldown should be persistent"

def test_conversational_betting_story_not_false_positive():
    user_id = 5264555563
    posts_count = 100
    story = "Это всё наркомания и саморазрушение, что видеоигры, что ставки на спорт. Не проебите свою жизнь пока не поздно."
    is_spam, reason = check_link_or_ad_spam(user_id, "b", story, posts_count=posts_count)
    assert is_spam is False, "Conversational life story discussing betting must not be flagged as ad scam"

    # Quoting the story should also not trigger
    quote = ">>12345 Это всё наркомания и саморазрушение, что видеоигры, что ставки на спорт.\nСогласен с аноном выше."
    is_spam, reason = check_link_or_ad_spam(7547199874, "b", quote, posts_count=posts_count)
    assert is_spam is False, "Quoting post discussing betting must not trigger ad scam"

    # Real betting ad with promo code / channel hook must still be flagged
    real_ad = "Ставки на спорт и легкий заработок! Забирай фрибет по промокоду WINNER"
    is_spam, reason = check_link_or_ad_spam(user_id, "b", real_ad, posts_count=posts_count)
    assert is_spam is True, "Real promo with call-to-action hooks must be flagged"

def test_casino_allowed_because_bot_has_casino():
    user_id = 5264555563
    posts_count = 100
    casino_messages = [
        "казино",
        "онлайн-казино",
        "погнали крутить казино в боте",
        "казино вулкан наебалово",
        "вавада и 1win",
        "проиграл 50000 шекелей в казино",
        "поднял джекпот в казино",
        "Поднимай бабло в 1win и казино вулкан вавада",
    ]
    for msg in casino_messages:
        is_spam, reason = check_link_or_ad_spam(user_id, "b", msg, posts_count=posts_count)
        assert is_spam is False, f"Casino mention '{msg}' must NOT trigger spam filter (bot has its own casino)"


