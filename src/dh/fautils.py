def get_persian_date(dformat=None) -> str | None:
    from datetime import datetime as datetime_datetime

    weeks = ["یکشنبه", "دوشنبه", "سه شنبه", "چهارشنبه", "پنج شنبه", "جمعه", "شنبه"]
    months = [
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    ]
    today = datetime_datetime.now()
    d = today.weekday()
    day = today.day
    month = today.month
    year = today.year
    if year <= 0:
        year = 2000
    if year < 100:
        year += 1900
    y = 1
    for i in range(0, 3000, 4):
        if year == i:
            y = 2
    for i in range(1, 3000, 4):
        if year == i:
            y = 3
    if y == 1:
        year -= ((month < 3 or (month == 3 and day < 21)) and 622) or 621
        if month == 1:
            month, day = (10, day + 10) if day < 21 else (11, day - 20)
        elif month == 2:
            month, day = (11, day + 11) if day < 20 else (12, day - 19)
        elif month == 3:
            month, day = (12, day + 9) if day < 21 else (1, day - 20)
        elif month == 4:
            month, day = (1, day + 11) if day < 21 else (2, day - 20)
        elif month in {5, 6}:
            month, day = (month - 3, day + 10) if day < 22 else (month - 2, day - 21)
        elif month in {7, 8, 9}:
            month, day = (month - 3, day + 9) if day < 23 else (month - 2, day - 22)
        elif month == 10:
            month, day = (7, day + 8) if day < 23 else (8, day - 22)
        elif month in {11, 12}:
            month, day = (month - 3, day + 9) if day < 22 else (month - 2, day - 21)
    if y == 2:
        year -= ((month < 3 or (month == 3 and day < 20)) and 622) or 621
        if month == 1:
            month, day = (10, day + 10) if day < 21 else (11, day - 20)
        elif month == 2:
            month, day = (11, day + 11) if day < 20 else (12, day - 19)
        elif month == 3:
            month, day = (12, day + 10) if day < 20 else (1, day - 19)
        elif month == 4:
            month, day = (1, day + 12) if day < 20 else (2, day - 19)
        elif month == 5:
            month, day = (2, day + 11) if day < 21 else (3, day - 20)
        elif month == 6:
            month, day = (3, day + 11) if day < 21 else (4, day - 20)
        elif month == 7:
            month, day = (4, day + 10) if day < 22 else (5, day - 21)
        elif month == 8:
            month, day = (5, day + 10) if day < 22 else (6, day - 21)
        elif month == 9:
            month, day = (6, day + 10) if day < 22 else (7, day - 21)
        elif month == 10:
            month, day = (7, day + 9) if day < 22 else (8, day - 21)
        elif month == 11:
            month, day = (8, day + 10) if day < 21 else (9, day - 20)
        elif month == 12:
            month, day = (9, day + 10) if day < 21 else (10, day - 20)
    if y == 3:
        year -= ((month < 3 or (month == 3 and day < 21)) and 622) or 621
        if month == 1:
            month, day = (10, day + 11) if day < 20 else (11, day - 19)
        elif month == 2:
            month, day = (11, day + 12) if day < 19 else (12, day - 18)
        elif month == 3:
            month, day = (12, day + 10) if day < 21 else (1, day - 20)
        elif month == 4:
            month, day = (1, day + 11) if day < 21 else (2, day - 20)
        elif month in {5, 6}:
            month, day = (month - 3, day + 10) if day < 22 else (month - 2, day - 21)
        elif month in {7, 8, 9}:
            month, day = (month - 3, day + 9) if day < 23 else (month - 2, day - 22)
        elif month == 10:
            month, day = (7, day + 8) if day < 23 else (8, day - 22)
        elif month in {11, 12}:
            month, day = (month - 3, day + 9) if day < 22 else (month - 2, day - 21)
    if dformat is None:
        return f"{weeks[d]} {day} {months[month - 1]} {year}"
    if dformat == "y/m/d":
        return f"{year}/{month}/{day}"
    if dformat == "d/m/y":
        return f"{day}/{month}/{year}"
    return None


def georgian_to_hijri(year: int, month: int, day: int) -> str:
    from datetime import date as datetime_date

    weekdays: list[str] = [
        "دو شنبه",
        "سه شنبه",
        "چهار شنبه",
        "پنج شنبه",
        "جمعه",
        "شنبه",
        "یکشنبه",
    ]
    months: list[str] = [
        "فروردین",
        "اردیبهشت",
        "خرداد",
        "تیر",
        "مرداد",
        "شهریور",
        "مهر",
        "آبان",
        "آذر",
        "دی",
        "بهمن",
        "اسفند",
    ]
    jy, jm, jd = gregorian_to_jalali(year, month, day)
    weekday_index: int = datetime_date(year, month, day).weekday()
    weekday: str = weekdays[weekday_index]
    return f"{weekday}  {to_persian_digits(str(jd))}  {months[jm - 1]}  {to_persian_digits(str(jy))}"


def to_persian_digits(s: str) -> str:
    from string import digits as string_digits

    return s.translate(str.maketrans(string_digits, "۰۱۲۳۴۵۶۷۸۹"))


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_days: list[int] = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2: int = gy - 1600
    gm2: int = gm - 1
    gd2: int = gd - 1
    g_day_no: int = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    g_day_no += g_days[gm2] + gd2
    j_day_no: int = g_day_no - 79
    j_np: int = j_day_no // 12053
    j_day_no %= 12053
    jy: int = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    if j_day_no < 186:
        jm = 1 + j_day_no // 31
        jd = 1 + j_day_no % 31
    else:
        j_day_no -= 186
        jm = 7 + j_day_no // 30
        jd = 1 + j_day_no % 30
    return jy, jm, jd
