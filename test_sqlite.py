import asyncio
import sqlite3
import json

async def main():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE Backlinks (target_post_num INT, source_post_num INT)")
    db.executemany("INSERT INTO Backlinks VALUES (?, ?)", [(1, 10), (1, 11), (2, 20), (3, 30)])

    ids = [1, 2, 4]
    ids_json = json.dumps(ids)

    q = """
        SELECT target_post_num, json_group_array(source_post_num)
        FROM Backlinks
        JOIN json_each(?) ON target_post_num = json_each.value
        GROUP BY target_post_num
    """

    cursor = db.execute(q, (ids_json,))
    res = {}
    for row in cursor:
        res[row[0]] = json.loads(row[1])

    print(res)

asyncio.run(main())
