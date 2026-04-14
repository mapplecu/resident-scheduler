import sqlite3
import pandas as pd
from typing import List, Dict
import os

DB_PATH = "scheduler.db"

def init_db():
    # Destroy and recreate the database to pick up schema changes cleanly.
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Residents
    cursor.execute('''CREATE TABLE IF NOT EXISTS Residents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        year_pgy INTEGER NOT NULL
                    )''')

    # 2. Rotations (stress 1-10; default 5)
    cursor.execute('''CREATE TABLE IF NOT EXISTS Rotations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        min_total INTEGER,
                        max_total INTEGER,
                        min_interns INTEGER,
                        max_interns INTEGER,
                        min_seniors INTEGER,
                        max_seniors INTEGER,
                        stress INTEGER DEFAULT 5
                    )''')

    # 3. Electives
    cursor.execute('''CREATE TABLE IF NOT EXISTS Electives (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL
                    )''')

    # 4. Requests (Soft)
    cursor.execute('''CREATE TABLE IF NOT EXISTS Requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        resident_name TEXT,
                        rotation_name TEXT,
                        month INTEGER,
                        weight INTEGER
                    )''')

    # 5. Hard Blocks
    cursor.execute('''CREATE TABLE IF NOT EXISTS Hard_Blocks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        resident_name TEXT,
                        rotation_name TEXT,
                        month INTEGER
                    )''')

    # 6. PGY Requirements
    cursor.execute('''CREATE TABLE IF NOT EXISTS Pgy_Requirements (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pgy_level INTEGER,
                        rotation_name TEXT,
                        min_months INTEGER,
                        max_months INTEGER
                    )''')

    # 7. Forbidden Adjacencies
    cursor.execute('''CREATE TABLE IF NOT EXISTS Forbidden_Adjacencies (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        rotation_1 TEXT,
                        rotation_2 TEXT
                    )''')

    conn.commit()
    conn.close()

# --- GENERIC DB OPS ---
def fetch_all(table_name):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def delete_row(table_name, row_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {table_name} WHERE id=?", (row_id,))
    conn.commit()
    conn.close()

def clear_all(table_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {table_name}")
    conn.commit()
    conn.close()

# --- SPECIFIC INSERTS ---
def add_resident(name: str, year: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Residents (name, year_pgy) VALUES (?, ?)", (name, year))
    conn.commit()
    conn.close()

def add_rotation(name, min_tot, max_tot, min_int, max_int, min_sen, max_sen, stress=5):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO Rotations
                      (name, min_total, max_total, min_interns, max_interns, min_seniors, max_seniors, stress)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                   (name, min_tot, max_tot, min_int, max_int, min_sen, max_sen, stress))
    conn.commit()
    conn.close()

def update_rotation(row_id, name, min_tot, max_tot, min_int, max_int, min_sen, max_sen, stress=5):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''UPDATE Rotations
                      SET name=?, min_total=?, max_total=?, min_interns=?, max_interns=?,
                          min_seniors=?, max_seniors=?, stress=?
                      WHERE id=?''',
                   (name, min_tot, max_tot, min_int, max_int, min_sen, max_sen, stress, row_id))
    conn.commit()
    conn.close()

def add_elective(name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Electives (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def add_request(res_name, rot_name, month, weight):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO Requests (resident_name, rotation_name, month, weight)
                      VALUES (?, ?, ?, ?)''', (res_name, rot_name, month, weight))
    conn.commit()
    conn.close()

def add_hard_block(res_name, rot_name, month):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO Hard_Blocks (resident_name, rotation_name, month)
                      VALUES (?, ?, ?)''', (res_name, rot_name, month))
    conn.commit()
    conn.close()

def add_pgy_requirement(pgy_level, rot_name, min_mo, max_mo):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO Pgy_Requirements (pgy_level, rotation_name, min_months, max_months)
                      VALUES (?, ?, ?, ?)''', (pgy_level, rot_name, min_mo, max_mo))
    conn.commit()
    conn.close()

def add_forbidden_adjacency(rot1, rot2):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO Forbidden_Adjacencies (rotation_1, rotation_2)
                      VALUES (?, ?)''', (rot1, rot2))
    conn.commit()
    conn.close()

def save_schedule(df: pd.DataFrame):
    conn = sqlite3.connect(DB_PATH)
    df.to_sql("Saved_Schedule", conn, if_exists="replace", index=False)
    conn.close()

def load_schedule() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql("SELECT * FROM Saved_Schedule", conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df

init_db()
