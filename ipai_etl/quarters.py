"""Quarter calendar and the monitoring window."""
import calendar
from datetime import date, timedelta


def qlabel(q, y):
    return f"Q{q}-{y}"


def parse_label(label):
    q, y = label.split("-")
    return int(q[1]), int(y)


def qidx(label):
    q, y = parse_label(label)
    return y * 4 + q - 1


def from_idx(i):
    return qlabel(i % 4 + 1, i // 4)


def quarter_end(label):
    q, y = parse_label(label)
    m = 3 * q
    return date(y, m, calendar.monthrange(y, m)[1])


def latest_completed_quarter(today):
    """Latest quarter whose end date is strictly in the past."""
    q = (today.month - 1) // 3 + 1
    y = today.year
    cur_start_idx = y * 4 + q - 1
    return from_idx(cur_start_idx - 1)


def window(label, start_day, end_day):
    e = quarter_end(label)
    return e + timedelta(days=start_day), e + timedelta(days=end_day)


def expected_quarters(first, last):
    return [from_idx(i) for i in range(qidx(first), qidx(last) + 1)]
