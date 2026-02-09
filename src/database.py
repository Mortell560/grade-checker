from __future__ import annotations

from typing import Any, Sequence

import aiosqlite

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def execute(self, query: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()

            # For statements that don't return rows (INSERT/UPDATE/CREATE/etc.)
            # SQLite reports no result columns via cursor.description.
            if cursor.description is None:
                await cursor.close()
                return []

            rows = await cursor.fetchall()
            await cursor.close()
            return rows
        
    async def create_tables(self) -> None:
        await self.execute("""
            CREATE TABLE IF NOT EXISTS grades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student TEXT,
                year INTEGER,
                semester INTEGER,
                module_code TEXT NOT NULL,
                name TEXT NOT NULL,
                date DATE NOT NULL,
                note TEXT,
                avg_note TEXT,
                rank TEXT,
                appreciation TEXT
            );
        """)
        await self.execute("""
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
                ec TEXT
            );
        """)
        await self.execute("""
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

        # Lightweight migrations for existing DBs.
        await self._ensure_column("grades", "student", "TEXT")
        await self._ensure_column("grades", "year", "INTEGER")
        await self._ensure_column("grades", "semester", "INTEGER")
        await self._ensure_column("modules", "ec", "TEXT")

        # Unique key to dedupe and enable safe upserts.
        try:
            await self.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_grades_key ON grades(student, year, semester, module_code, name, date);"
            )
        except aiosqlite.Error:
            # If the table already contains duplicates, SQLite will refuse to create the index.
            # The app can still run without the index (it just can't rely on conflict upserts).
            pass

    async def _ensure_column(self, table: str, column: str, column_type: str) -> None:
        rows = await self.execute(f"PRAGMA table_info({table});")
        existing = {r[1] for r in rows}  # name is the 2nd column
        if column in existing:
            return
        await self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type};")

    async def insert_grade(self, module_code: str, name: str, date: str, note: str, avg_note: str, rank: str, appreciation: str, year: int) -> None:
        await self.execute("""
            INSERT INTO grades (module_code, name, date, note, avg_note, rank, appreciation, year)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """, (module_code, name, date, note, avg_note, rank, appreciation, year))

    async def get_grade_by_key(
        self,
        *,
        student: str,
        year: int,
        semester: int,
        module_code: str,
        name: str,
        date: str,
    ) -> list[tuple[Any, ...]]:
        return await self.execute(
            """
            SELECT id, note, avg_note, rank, appreciation
            FROM grades
            WHERE student = ? AND year = ? AND semester = ? AND module_code = ? AND name = ? AND date = ?
            LIMIT 1;
            """,
            (student, year, semester, module_code, name, date),
        )

    async def upsert_grade(
        self,
        *,
        student: str,
        year: int,
        semester: int,
        module_code: str,
        name: str,
        date: str,
        note: str,
        avg_note: str,
        rank: str,
        appreciation: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """
                UPDATE grades
                SET note = ?, avg_note = ?, rank = ?, appreciation = ?
                WHERE student = ? AND year = ? AND semester = ? AND module_code = ? AND name = ? AND date = ?;
                """,
                (
                    note,
                    avg_note,
                    rank,
                    appreciation,
                    student,
                    year,
                    semester,
                    module_code,
                    name,
                    date,
                ),
            )
            await conn.commit()

            if cursor.rowcount == 0:
                await conn.execute(
                    """
                    INSERT INTO grades (student, year, semester, module_code, name, date, note, avg_note, rank, appreciation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        student,
                        year,
                        semester,
                        module_code,
                        name,
                        date,
                        note,
                        avg_note,
                        rank,
                        appreciation,
                    ),
                )
                await conn.commit()

    async def insert_module(self, module_code: str, ue_code: str, title_fr: str, coef: float, bloc_code: str, note: str, avg_note: str, rank: str, ec: str) -> None:
        await self.execute("""
            INSERT INTO modules (module_code, ue_code, title_fr, coef, bloc_code, note, avg_note, rank, ec)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (module_code, ue_code, title_fr, coef, bloc_code, note, avg_note, rank, ec))

    async def insert_ue(self, ue_code: str, title_fr: str, ects: float, note: str, avg_note: str, rank: str, resultat: str) -> None:
        await self.execute("""
            INSERT INTO ue (ue_code, title_fr, ects, note, avg_note, rank, resultat)
            VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (ue_code, title_fr, ects, note, avg_note, rank, resultat))

    async def get_current_grades(self) -> list[tuple[Any, ...]]:
        return await self.execute("SELECT * FROM grades;")

    async def get_grades_for_semester(self, *, student: str, year: int, semester: int) -> list[tuple[Any, ...]]:
        return await self.execute(
            "SELECT * FROM grades WHERE student = ? AND year = ? AND semester = ?;",
            (student, year, semester),
        )