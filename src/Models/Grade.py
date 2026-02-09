class Grade:
    def __init__(self, module_code: str, name: str, date: str, note: str, avg_note: str, rank: str, appreciation: str):
        self.id = None  # Will be set when inserted into DB
        self.module_code = module_code
        self.name = name
        self.date = date
        self.note = note
        self.avg_note = avg_note
        self.rank = rank
        self.appreciation = appreciation
