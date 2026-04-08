import json
import sqlite3
from datetime import datetime
from pathlib import Path

from models.analysis import AnalysisResult
from models.post import Post
from models.trade import TradeRecord

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "trader.db"


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS seen_posts (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                url TEXT,
                has_media INTEGER DEFAULT 0,
                first_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL,
                is_relevant INTEGER NOT NULL,
                reasoning TEXT NOT NULL,
                sentiment REAL NOT NULL,
                affected_sectors TEXT NOT NULL,
                affected_tickers TEXT NOT NULL,
                confidence REAL NOT NULL,
                direction TEXT NOT NULL,
                urgency TEXT NOT NULL,
                analyzed_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES seen_posts(id)
            );

            CREATE TABLE IF NOT EXISTS pending_analyses (
                post_id TEXT PRIMARY KEY,
                queued_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES seen_posts(id)
            );

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                order_id TEXT NOT NULL,
                status TEXT NOT NULL,
                executed_at TEXT NOT NULL,
                entry_price REAL,
                analysis_confidence REAL NOT NULL,
                analysis_sentiment REAL NOT NULL,
                FOREIGN KEY (post_id) REFERENCES seen_posts(id)
            );
        """)
        self.conn.commit()

    def has_seen_post(self, post_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_posts WHERE id = ?", (post_id,)
        ).fetchone()
        return row is not None

    def save_post(self, post: Post) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO seen_posts (id, text, created_at, url, has_media, first_seen_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                post.id,
                post.text,
                post.created_at.isoformat(),
                post.url,
                int(post.has_media),
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def save_analysis(self, post_id: str, analysis: AnalysisResult) -> None:
        self.conn.execute(
            """INSERT INTO analyses
               (post_id, is_relevant, reasoning, sentiment, affected_sectors,
                affected_tickers, confidence, direction, urgency, analyzed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post_id,
                int(analysis.is_relevant),
                analysis.reasoning,
                analysis.sentiment,
                json.dumps(analysis.affected_sectors),
                json.dumps(analysis.affected_tickers),
                analysis.confidence,
                analysis.direction,
                analysis.urgency,
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def save_trade(self, trade: TradeRecord) -> None:
        self.conn.execute(
            """INSERT INTO trades
               (post_id, symbol, side, quantity, order_id, status,
                executed_at, entry_price, analysis_confidence, analysis_sentiment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.post_id,
                trade.symbol,
                trade.side,
                trade.quantity,
                trade.order_id,
                trade.status,
                trade.executed_at.isoformat(),
                trade.entry_price,
                trade.analysis_confidence,
                trade.analysis_sentiment,
            ),
        )
        self.conn.commit()

    def queue_pending_analysis(self, post_id: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO pending_analyses (post_id, queued_at) VALUES (?, ?)",
            (post_id, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_pending_analyses(self) -> list[tuple[str, AnalysisResult]]:
        rows = self.conn.execute(
            """SELECT a.post_id, a.is_relevant, a.reasoning, a.sentiment,
                      a.affected_sectors, a.affected_tickers, a.confidence,
                      a.direction, a.urgency
               FROM pending_analyses pa
               JOIN analyses a ON a.post_id = pa.post_id
               ORDER BY pa.queued_at ASC"""
        ).fetchall()
        return [
            (
                row["post_id"],
                AnalysisResult(
                    is_relevant=bool(row["is_relevant"]),
                    reasoning=row["reasoning"],
                    sentiment=row["sentiment"],
                    affected_sectors=json.loads(row["affected_sectors"]),
                    affected_tickers=json.loads(row["affected_tickers"]),
                    confidence=row["confidence"],
                    direction=row["direction"],
                    urgency=row["urgency"],
                ),
            )
            for row in rows
        ]

    def clear_pending_analysis(self, post_id: str) -> None:
        self.conn.execute("DELETE FROM pending_analyses WHERE post_id = ?", (post_id,))
        self.conn.commit()

    def get_trades_today(self) -> list[dict]:
        today = datetime.now().date().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE executed_at >= ?", (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_open_trade_count(self) -> int:
        rows = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM trades WHERE status = 'filled'"
        ).fetchone()
        return rows["cnt"] if rows else 0

    def close(self) -> None:
        self.conn.close()
