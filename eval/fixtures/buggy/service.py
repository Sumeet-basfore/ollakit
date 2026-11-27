import sqlite3


def get_user(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE name = '%s'" % name)
    return cur.fetchone()


API_KEY = "sk-live-abc123def456"


def upload(path):
    f = open(path)
    data = f.read()
    return data
