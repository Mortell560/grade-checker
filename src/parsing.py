from bs4 import BeautifulSoup

from Models.Grade import Grade


def _clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = " ".join(value.split())

    # Normalize common dash placeholders.
    if value in {"—", "-", "--", "––", "&mdash;"}:
        return "—"
    return value


def _cell_text(cell) -> str:
    if cell is None:
        return ""
    return _clean_text(cell.get_text(" ", strip=True))


def parse_grades(html_content: str) -> list[Grade]:
    soup = BeautifulSoup(html_content, "html.parser")

    grades: list[Grade] = []

    # The "Épreuves" table(s) usually have an id like "Tests12025".
    for table in soup.select('table[id^="Tests"]'):
        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) < 7:
                continue

            module_div = cells[0].select_one("div.courseLine")
            module_code = _clean_text(module_div.get("data-code", "")) if module_div else ""

            module_code = _cell_text(cells[0])
            name = _cell_text(cells[1])
            date = _cell_text(cells[2])
            note = _cell_text(cells[3])
            avg_note = _cell_text(cells[4])
            rank = _cell_text(cells[5])
            appreciation = _cell_text(cells[6])

            grades.append(
                Grade(
                    module_code=module_code,
                    name=name,
                    date=date,
                    note=note,
                    avg_note=avg_note,
                    rank=rank,
                    appreciation=appreciation,
                )
            )

    return grades


def parse_semester_average(html_content: str) -> str:
    """Extract the displayed semester average (e.g. '17,730') from the semester HTML."""
    soup = BeautifulSoup(html_content, "html.parser")
    avg = soup.select_one(".semesterAverage")
    if avg is None:
        return "—"
    return _clean_text(avg.get_text(" ", strip=True))