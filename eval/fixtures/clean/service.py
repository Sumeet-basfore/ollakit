import os
import sqlite3


def get_user(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE name = ?", (name,))
    return cur.fetchone()


API_KEY = os.environ["SERVICE_API_KEY"]


def upload(path):
    with open(path) as f:
        data = f.read()
    return data
