import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setting up environment variables
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

from common.anon_identity import generate_anon_name, get_anon_id, get_referral_code

def test_generate_anon_name_empty_user_id():
    assert generate_anon_name(0) == "Анонимус"
    assert generate_anon_name(None) == "Анонимус"
    assert generate_anon_name(False) == "Анонимус"
    assert generate_anon_name(0, stream="en") == "Anonymous"

def test_generate_anon_name_deterministic():
    name1 = generate_anon_name(12345)
    name2 = generate_anon_name(12345)
    assert name1 == name2

def test_generate_anon_name_format():
    user_id = 987654321
    name_ru = generate_anon_name(user_id, stream="ru")
    name_en = generate_anon_name(user_id, stream="en")
    
    assert name_ru.startswith("Анон [") and name_ru.endswith("]")
    assert name_en.startswith("Anon [") and name_en.endswith("]")

    anon_id_ru = get_anon_id(user_id, stream="ru")
    anon_id_en = get_anon_id(user_id, stream="en")
    
    # 6 letters + 1 digit = 7 chars
    assert len(anon_id_ru) == 7, f"Expected 7 chars, got {anon_id_ru}"
    assert len(anon_id_en) == 7, f"Expected 7 chars, got {anon_id_en}"
    assert anon_id_ru[-1].isdigit()
    assert anon_id_en[-1].isdigit()

def test_generate_anon_name_different_users():
    name1 = generate_anon_name(11111)
    name2 = generate_anon_name(22222)
    assert name1 != name2

def test_referral_code():
    code = get_referral_code(7716348189)
    assert len(code) == 7
    assert code.isalnum()
    assert code[-1].isdigit()
    print(f"Test referral code for 7716348189: {code}")

if __name__ == "__main__":
    test_generate_anon_name_empty_user_id()
    test_generate_anon_name_deterministic()
    test_generate_anon_name_format()
    test_generate_anon_name_different_users()
    test_referral_code()
    print("All test_generate_anon_name tests passed successfully!")
