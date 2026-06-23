import hashlib
import time
from Dubsite_tgach.security import verify_pow, POW_CACHE, DEFAULT_POW_DIFFICULTY

def test_verify_pow_difficulty_zero():
    """If difficulty is 0, it should always return True without checking the cache."""
    # Ensure cache is empty for this challenge
    challenge = "test_chal_diff_0"
    POW_CACHE.pop(challenge, None)

    assert verify_pow(challenge, "any_nonce", difficulty=0) is True

def test_verify_pow_invalid_inputs():
    """Should return False if challenge or nonce are empty, or if challenge not in cache."""
    challenge = "test_chal_invalid"

    # 1. Empty challenge
    assert verify_pow("", "some_nonce") is False

    # 2. Empty nonce
    POW_CACHE[challenge] = time.time() + 600
    assert verify_pow(challenge, "") is False

    # 3. Challenge not in cache
    POW_CACHE.pop(challenge, None)
    assert verify_pow(challenge, "some_nonce") is False

def test_verify_pow_valid_nonce():
    """Given a valid nonce, it should return True and remove the challenge from cache."""
    challenge = "test_chal_valid"
    difficulty = 2

    # Find a valid nonce for difficulty 2
    nonce = 0
    target = "0" * difficulty
    while True:
        if hashlib.sha256(f"{challenge}{nonce}".encode()).hexdigest().startswith(target):
            valid_nonce = str(nonce)
            break
        nonce += 1

    POW_CACHE[challenge] = time.time() + 600

    # Verify the nonce
    assert verify_pow(challenge, valid_nonce, difficulty=difficulty) is True

    # Verify the challenge was removed from cache
    assert challenge not in POW_CACHE

def test_verify_pow_invalid_nonce():
    """Given an invalid nonce, it should return False and keep the challenge in cache."""
    challenge = "test_chal_invalid_nonce"
    difficulty = 2

    # Find an invalid nonce for difficulty 2
    nonce = 0
    target = "0" * difficulty
    while True:
        if not hashlib.sha256(f"{challenge}{nonce}".encode()).hexdigest().startswith(target):
            invalid_nonce = str(nonce)
            break
        nonce += 1

    POW_CACHE[challenge] = time.time() + 600

    # Verify the nonce
    assert verify_pow(challenge, invalid_nonce, difficulty=difficulty) is False

    # Verify the challenge was kept in cache
    assert challenge in POW_CACHE
