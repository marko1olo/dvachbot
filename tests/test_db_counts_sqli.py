import pytest
import sqlite3
import tempfile
import pathlib

# We will test the _db_counts explicitly
import bot_live_status

def test_db_counts_no_sqli():
    # Setup dummy database
    with tempfile.NamedTemporaryFile(delete=False) as f:
        db_path = pathlib.Path(f.name)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Create the needed tables
    cur.execute("CREATE TABLE Users (id INTEGER, status TEXT)")
    cur.execute("CREATE TABLE Posts (id INTEGER)")
    cur.execute("CREATE TABLE PostCopies (id INTEGER)")
    cur.execute("CREATE TABLE BroadcastQueue (id INTEGER, is_sent_to_tg INTEGER)")
    cur.execute("CREATE TABLE DeliveryQueue (id INTEGER, status TEXT)")
    conn.commit()
    conn.close()

    # Overwrite DB_PATH in bot_live_status
    bot_live_status.DB_PATH = db_path

    res = bot_live_status._db_counts()

    # Check that counts are properly retrieved and no error occurred due to missing tables
    assert res.get("error") is None or "no such table" not in res.get("error", "")
    assert res.get("Users") == 0
    assert res.get("Posts") == 0
    assert res.get("PostCopies") == 0
    assert res.get("BroadcastQueue") == 0

    # Clean up
    db_path.unlink()
