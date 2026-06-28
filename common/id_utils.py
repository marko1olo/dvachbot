import hashlib

def generate_negative_id(token: str) -> int:
    hash_val = hashlib.sha256(token.encode()).hexdigest()
    val = int(hash_val[:8], 16)
    return -(val % 2147483647) - 1
