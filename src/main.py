import os
import time
import asyncio
from typing import Optional
from http.cookiejar import Cookie
from datetime import datetime, timezone

import httpx

from database import Database
from parsing import parse_grades
from webhook import send_webhook


LOGIN_URL = (
    f"{os.getenv('OASIS_BASE_URL', 'https://polytech-saclay.oasis.aouka.org')}/prod/bo/core/Router/Ajax/ajax.php"
    "?targetProject=oasis_polytech_paris"
    "&route=BO\\Connection\\User::login"
)

SEMESTER_URL = (
    f"{os.getenv('OASIS_BASE_URL', 'https://polytech-saclay.oasis.aouka.org')}/prod/bo/core/Router/Ajax/ajax.php"
    "?targetProject=oasis_polytech_paris"
    "&route=Oasis\\Common\\Model\\Cursus\\StudentCursus\\StudentCursus::reload_semester"
)

# Set this to the cookie name that contains the token (e.g. "token", "jwt", etc.)
TOKEN_COOKIE_NAME = os.environ.get(
    "OASIS_TOKEN_COOKIE_NAME",
    "bo_oasis_polytech_parisSession",
)
CURRENT_YEAR_COOKIE = os.environ.get(
    "OASIS_CURRENT_YEAR_COOKIE",
    "bo_oasis_polytech_parisyear",
)

DB_PATH = os.environ.get("DB_PATH", "grades.db")
SYNC_INTERVAL_SECONDS = int(os.environ.get("SYNC_INTERVAL_SECONDS", "3600"))

def _iter_cookiejar(cookies: httpx.Cookies):
    # httpx stores cookies in an underlying http.cookiejar.CookieJar.
    # Iterating the jar yields http.cookiejar.Cookie objects.
    return cookies.jar


def _get_cookie(session: httpx.AsyncClient, name: str) -> Optional[Cookie]:
    for c in _iter_cookiejar(session.cookies):
        if c.name == name:
            return c
    return None


def _is_expired(cookie: Cookie, skew_seconds: int = 30) -> bool:
    # If cookie.expires is None => session cookie; treat as not-expired here.
    if cookie.expires is None:
        return False
    return cookie.expires <= int(time.time()) + skew_seconds


async def _login(session: httpx.AsyncClient, login: str, password: str) -> None:
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "fr-FR,fr;q=0.8",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": os.getenv("OASIS_BASE_URL", "https://polytech-saclay.oasis.aouka.org"),
        "Referer": os.getenv("OASIS_BASE_URL", "https://polytech-saclay.oasis.aouka.org") + "/?",
    }
    data = {"login": login, "password": password, "url": ""}

    resp = await session.post(LOGIN_URL, headers=headers, data=data)
    print(f"Login response: {resp.status_code}")
    resp.raise_for_status()
    # session.cookies is now updated in-memory if server returned Set-Cookie


async def ensure_valid_session(session: httpx.AsyncClient, login: str, password: str) -> None:
    token_cookie = _get_cookie(session, TOKEN_COOKIE_NAME)
    current_year_cookie = _get_cookie(session, CURRENT_YEAR_COOKIE)

    if (
        token_cookie is None
        or _is_expired(token_cookie)
        or current_year_cookie is None
        or _is_expired(current_year_cookie)
    ):
        await _login(session, login, password)


async def _post_with_retry_on_auth(
    session: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    data: dict[str, str],
    login: str,
    password: str,
) -> httpx.Response:
    """POST and if auth fails (401/403), re-login and retry once."""
    await ensure_valid_session(session, login, password)
    resp = await session.post(url, headers=headers, data=data)
    if resp.status_code in (401, 403):
        await _login(session, login, password)
        resp = await session.post(url, headers=headers, data=data)
    resp.raise_for_status()
    return resp


def _extract_html(resp: httpx.Response) -> str:
    content_type = resp.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = resp.json()
        if isinstance(payload, dict):
            for key in ("html", "content", "data", "result"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value
        # Fallback to stringified JSON
        return resp.text
    return resp.text


def _get_year_value(session: httpx.AsyncClient) -> str:
    cookie = _get_cookie(session, CURRENT_YEAR_COOKIE)
    if cookie is not None and getattr(cookie, "value", ""):
        return str(cookie.value)
    # Allow overriding explicitly.
    return os.environ.get("OASIS_YEAR", CURRENT_YEAR_COOKIE)


async def _fetch_semester_html(
    session: httpx.AsyncClient,
    *,
    student: str,
    year_value: str,
    semester_in_year: int,
    tab: str,
    login: str,
    password: str,
) -> str:
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "fr-FR,fr;q=0.8",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": os.getenv("OASIS_BASE_URL", "https://polytech-saclay.oasis.aouka.org"),
        "Referer": os.getenv("OASIS_BASE_URL", "https://polytech-saclay.oasis.aouka.org") + "/?",
    }
    data = {
        "student": student,
        "year": year_value,
        "semester_in_year": str(semester_in_year),
        "tab": tab,
    }

    resp = await _post_with_retry_on_auth(
        session,
        SEMESTER_URL,
        headers=headers,
        data=data,
        login=login,
        password=password,
    )
    return _extract_html(resp)


async def _sync_grades_for_semester(
    db: Database,
    *,
    student: str,
    year: int,
    semester: int,
    grades,
) -> tuple[int, int, list[str]]:
    """Returns (new_count, updated_count, details)."""
    new_count = 0
    updated_count = 0
    details: list[str] = []

    for grade in grades:
        existing = await db.get_grade_by_key(
            student=student,
            year=year,
            semester=semester,
            module_code=grade.module_code,
            name=grade.name,
            date=grade.date,
        )

        if not existing:
            new_count += 1
            details.append(
                f"NEW S{semester} {grade.module_code} | {grade.name} | {grade.date} | {grade.avg_note}"
            )
        else:
            _id, old_note, old_avg, old_rank, old_app = existing[0]
            if (
                (old_note or "") != (grade.note or "")
                or (old_avg or "") != (grade.avg_note or "")
                or (old_rank or "") != (grade.rank or "")
                or (old_app or "") != (grade.appreciation or "")
            ):
                updated_count += 1
                details.append(
                    f"UPD S{semester} {grade.module_code} | {grade.name} | {grade.date} | {old_avg}->{grade.avg_note}"
                )

        await db.upsert_grade(
            student=student,
            year=year,
            semester=semester,
            module_code=grade.module_code,
            name=grade.name,
            date=grade.date,
            note=grade.note,
            avg_note=grade.avg_note,
            rank=grade.rank,
            appreciation=grade.appreciation,
        )

    return new_count, updated_count, details


async def sync_once(*, session: httpx.AsyncClient, db: Database, login: str, password: str) -> None:
    await ensure_valid_session(session, login, password)

    # Resolve year from cookie when possible.
    year_value = _get_year_value(session)
    try:
        year_int = int(year_value)
    except ValueError:
        # If the server expects a non-numeric value, we still pass it along,
        # but use the current calendar year for DB bucketing.
        year_int = datetime.now(timezone.utc).year

    total_new = 0
    total_updated = 0
    all_details: list[str] = []

    # Fetch and sync semesters 1 and 2.
    for semester in (1, 2):
        html = await _fetch_semester_html(
            session,
            student=login,
            year_value=year_value,
            semester_in_year=semester,
            tab="Courses",
            login=login,
            password=password,
        )
        grades = parse_grades(html)
        new_count, updated_count, details = await _sync_grades_for_semester(
            db,
            student=login,
            year=year_int,
            semester=semester,
            grades=grades,
        )
        total_new += new_count
        total_updated += updated_count
        all_details.extend(details)

    if total_new or total_updated:
        max_lines = int(os.environ.get("WEBHOOK_MAX_LINES", "30"))
        lines = [
            f"New: {total_new} | Updated: {total_updated}",
        ]
        lines.extend(all_details[:max_lines])
        if len(all_details) > max_lines:
            lines.append(f"…and {len(all_details) - max_lines} more")
        await send_webhook("\n".join(lines))
    else:
        print("No grade changes detected.")


async def main() -> None:
    login = os.environ.get("OASIS_LOGIN", "")
    password = os.environ.get("OASIS_PASSWORD", "")
    if not login or not password:
        raise SystemExit("Set OASIS_LOGIN and OASIS_PASSWORD env vars.")

    db = Database(DB_PATH)
    await db.create_tables()

    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout) as session:
        print(f"Starting grade sync loop; interval={SYNC_INTERVAL_SECONDS}s")

        next_run = time.monotonic()
        while True:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            try:
                print(f"[{now}] Sync starting")
                await sync_once(session=session, db=db, login=login, password=password)
                print(f"[{now}] Sync done")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[{now}] Sync failed: {exc!r}")

            next_run += SYNC_INTERVAL_SECONDS
            sleep_for = max(0.0, next_run - time.monotonic())
            await asyncio.sleep(sleep_for)


if __name__ == "__main__":
    asyncio.run(main())