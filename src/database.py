import sqlite3 as sql

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def execute(self, query: str, params: tuple = ()):
        with sql.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.fetchall()
        
    def create_tables(self):
        self.execute("""
            CREATE TABLE IF NOT EXISTS grade (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_code TEXT NOT NULL,
                name TEXT NOT NULL,
                date DATE NOT NULL,
                note TEXT,
                avg_note TEXT,
                rank TEXT,
                appreciation TEXT,
                year INTEGER NOT NULL
            );
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_code TEXT NOT NULL,
                ue_code TEXT NOT NULL,
                title_fr TEXT NOT NULL,
                coef REAL NOT NULL,
                bloc_code TEXT NOT NULL,
                note TEXT,
                avg_note TEXT,
                rank TEXT,
                ec TEXT NOT NULL
            );
        """)
        self.execute("""
            CREATE TABLE IF NOT EXISTS ue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ue_code TEXT NOT NULL,
                title_fr TEXT NOT NULL,
                ects REAL NOT NULL,
                note TEXT,
                avg_note TEXT,
                rank TEXT,
                resultat TEXT NOT NULL
            );
        """)