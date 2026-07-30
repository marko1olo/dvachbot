import sqlite3
import json

conn = sqlite3.connect(':memory:')
c = conn.cursor()
c.execute("CREATE TABLE t (a, b, c)")
c.execute("CREATE INDEX idx1 ON t (a, b)")
c.execute("CREATE INDEX idx2 ON t (c)")

c.execute("SELECT * FROM pragma_index_list('t')")
indexes = c.fetchall()
print("Indexes:", indexes)

index_names = [idx[1] for idx in indexes]
print("Index names:", index_names)

c.execute(
    "SELECT j.value, p.name FROM json_each(?) j CROSS JOIN pragma_index_info(j.value) p",
    (json.dumps(index_names),)
)
rows = c.fetchall()
print("Batched:", rows)

c.execute("SELECT * FROM pragma_index_info('idx1')")
print("Single idx1:", c.fetchall())

c.execute("SELECT * FROM pragma_index_info('idx2')")
print("Single idx2:", c.fetchall())
