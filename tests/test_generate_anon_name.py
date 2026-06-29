import pytest
import os

# Setting up environment variables
os.environ["SECRET_KEY"] = "test"
os.environ["BOT_TOKEN"] = "test"
os.environ["OPENAI_API_KEY"] = "test"

# Do not mock sys.modules. We will load the main module and use it directly.
from main import generate_anon_name, NICK_PREFIXES, NICK_SUFFIXES

def test_generate_anon_name_empty_user_id():
    assert generate_anon_name(0) == "Анонимус"
    assert generate_anon_name(None) == "Анонимус"
    assert generate_anon_name(False) == "Анонимус"

def test_generate_anon_name_deterministic():
    name1 = generate_anon_name(12345)
    name2 = generate_anon_name(12345)
    assert name1 == name2

def test_generate_anon_name_format():
    user_id = 987654321
    name = generate_anon_name(user_id)
    assert " (#4321)" in name

    parts = name.split(" (#")
    assert len(parts) == 2

    nick_parts = parts[0].split("-")
    assert len(nick_parts) == 2
    assert nick_parts[0] in NICK_PREFIXES
    assert nick_parts[1] in NICK_SUFFIXES

def test_generate_anon_name_different_users():
    name1 = generate_anon_name(11111)
    name2 = generate_anon_name(22222)
    assert name1 != name2

def test_generate_anon_name_short_id():
    name = generate_anon_name(12)
    assert " (#12)" in name
