"""SQLite 存储：逐日份额、每日全A/宽基合计、上证指数。单位：份额=份，flow=元。"""
import sqlite3


def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS daily_share(
            date TEXT, code TEXT, shares REAL, PRIMARY KEY(date, code));
        CREATE TABLE IF NOT EXISTS daily_agg(
            date TEXT PRIMARY KEY, flow_all REAL, flow_broad REAL);
        CREATE TABLE IF NOT EXISTS daily_index(
            date TEXT PRIMARY KEY, close REAL);
        CREATE INDEX IF NOT EXISTS idx_share_date ON daily_share(date);
    """)
    conn.commit()
    return conn


def save_shares(conn: sqlite3.Connection, date: str, shares: dict[str, float]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO daily_share(date, code, shares) VALUES(?,?,?)",
        [(date, code, v) for code, v in shares.items()],
    )
    conn.commit()


def save_agg(conn: sqlite3.Connection, date: str, flow_all: float, flow_broad: float) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO daily_agg(date, flow_all, flow_broad) VALUES(?,?,?)",
        (date, flow_all, flow_broad),
    )
    conn.commit()


def save_index(conn: sqlite3.Connection, date: str, close: float) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO daily_index(date, close) VALUES(?,?)", (date, close))
    conn.commit()


def read_shares(conn: sqlite3.Connection, date: str) -> dict[str, float]:
    cur = conn.execute("SELECT code, shares FROM daily_share WHERE date=?", (date,))
    return {code: shares for code, shares in cur.fetchall()}


def latest_date_before(conn: sqlite3.Connection, date: str) -> str | None:
    cur = conn.execute(
        "SELECT MAX(date) FROM daily_share WHERE date < ?", (date,))
    return cur.fetchone()[0]


def read_agg_series(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        "SELECT date, flow_all, flow_broad FROM daily_agg ORDER BY date ASC")
    return [{"date": d, "flow_all": a, "flow_broad": b} for d, a, b in cur.fetchall()]


def read_index_map(conn: sqlite3.Connection) -> dict[str, float]:
    cur = conn.execute("SELECT date, close FROM daily_index")
    return {d: c for d, c in cur.fetchall()}
