import json

try:
    import orjson

    def fast_json_loads(data: str | bytes):
        if not data:
            return None
        return orjson.loads(data)

    def fast_json_dumps(obj, default=str) -> str:
        return orjson.dumps(obj, default=default).decode('utf-8')

except ImportError:
    def fast_json_loads(data: str | bytes):
        if not data:
            return None
        return json.loads(data)

    def fast_json_dumps(obj, default=str) -> str:
        return json.dumps(obj, ensure_ascii=False, default=default)
