import sqlite3
from datetime import datetime, timezone

DB_PATH = "mahjong.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        is_active INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS session_players (
        session_id INTEGER NOT NULL,
        player_id TEXT NOT NULL,
        seat TEXT,
        PRIMARY KEY (session_id, player_id),
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        played_at TEXT NOT NULL,
        winner_id TEXT NOT NULL,
        fan INTEGER NOT NULL,
        win_type TEXT NOT NULL,
        loser_id TEXT,
        notes TEXT,
        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS game_scores (
        game_id INTEGER NOT NULL,
        player_id TEXT NOT NULL,
        score_change INTEGER NOT NULL,
        PRIMARY KEY (game_id, player_id),
        FOREIGN KEY (game_id) REFERENCES games(game_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS score_adjustments (
        adjustment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        player_id TEXT NOT NULL,
        score_change INTEGER NOT NULL,
        reason TEXT,
        adjusted_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def get_active_session(guild_id: int, channel_id: int) -> int | None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT session_id
        FROM sessions
        WHERE guild_id = ?
          AND channel_id = ?
          AND is_active = 1
        ORDER BY session_id DESC
        LIMIT 1
    """, (str(guild_id), str(channel_id)))

    row = cur.fetchone()
    conn.close()

    return row[0] if row else None


def get_session_players(session_id: int) -> list[tuple[str, str]]:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT player_id, seat
        FROM session_players
        WHERE session_id = ?
        ORDER BY
            CASE seat
                WHEN 'East' THEN 1
                WHEN 'South' THEN 2
                WHEN 'West' THEN 3
                WHEN 'North' THEN 4
                ELSE 5
            END
    """, (session_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


def create_session(
    guild_id: int,
    channel_id: int,
    players: list[tuple[str, int]],
) -> int:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sessions (guild_id, channel_id, started_at, is_active)
        VALUES (?, ?, ?, 1)
    """, (str(guild_id), str(channel_id), utc_now()))

    session_id = cur.lastrowid

    for seat, player_id in players:
        cur.execute("""
            INSERT INTO session_players (session_id, player_id, seat)
            VALUES (?, ?, ?)
        """, (session_id, str(player_id), seat))

    conn.commit()
    conn.close()

    return session_id


def insert_game(
    session_id: int,
    winner_id: int,
    fan: int,
    win_type: str,
    loser_id: int | None,
    notes: str | None,
    score_changes: list[tuple[str, int]],
) -> int:
    return insert_game_with_played_at(
        session_id=session_id,
        played_at=utc_now(),
        winner_id=winner_id,
        fan=fan,
        win_type=win_type,
        loser_id=loser_id,
        notes=notes,
        score_changes=score_changes,
    )


def insert_game_with_played_at(
    session_id: int,
    played_at: str,
    winner_id: int,
    fan: int,
    win_type: str,
    loser_id: int | None,
    notes: str | None,
    score_changes: list[tuple[str, int]],
) -> int:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO games (
            session_id,
            played_at,
            winner_id,
            fan,
            win_type,
            loser_id,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        played_at,
        str(winner_id),
        fan,
        win_type,
        str(loser_id) if loser_id else None,
        notes,
    ))

    game_id = cur.lastrowid

    for player_id, score_change in score_changes:
        cur.execute("""
            INSERT INTO game_scores (game_id, player_id, score_change)
            VALUES (?, ?, ?)
        """, (game_id, player_id, score_change))

    conn.commit()
    conn.close()

    return game_id


def get_latest_game_for_session(session_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            g.game_id,
            g.winner_id,
            g.fan,
            g.win_type,
            g.loser_id,
            g.notes,
            g.played_at
        FROM games g
        WHERE g.session_id = ?
        ORDER BY g.game_id DESC
        LIMIT 1
    """, (session_id,))

    row = cur.fetchone()
    conn.close()

    return row


def delete_game(game_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM game_scores WHERE game_id = ?", (game_id,))
    cur.execute("DELETE FROM games WHERE game_id = ?", (game_id,))

    conn.commit()
    conn.close()


def end_session(session_id: int):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        UPDATE sessions
        SET is_active = 0,
            ended_at = ?
        WHERE session_id = ?
    """, (utc_now(), session_id))

    conn.commit()
    conn.close()


def add_score_adjustment(
    guild_id: int,
    player_id: int,
    score_change: int,
    reason: str | None,
):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO score_adjustments (
            guild_id,
            player_id,
            score_change,
            reason,
            adjusted_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        str(guild_id),
        str(player_id),
        score_change,
        reason,
        utc_now(),
    ))

    conn.commit()
    conn.close()


def get_monthly_leaderboard(guild_id: int, month: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        WITH game_totals AS (
            SELECT
                gs.player_id,
                COUNT(DISTINCT g.game_id) AS games_played,
                SUM(CASE WHEN g.winner_id = gs.player_id THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN g.winner_id = gs.player_id THEN g.fan ELSE 0 END) AS total_fan_won,
                SUM(CASE WHEN g.winner_id = gs.player_id AND g.win_type = '自摸' THEN 1 ELSE 0 END) AS self_draw_wins,
                SUM(CASE WHEN g.loser_id = gs.player_id AND g.win_type = '食糊' THEN 1 ELSE 0 END) AS discard_losses,
                SUM(gs.score_change) AS game_score
            FROM game_scores gs
            JOIN games g ON g.game_id = gs.game_id
            JOIN sessions s ON s.session_id = g.session_id
            WHERE s.guild_id = ?
              AND substr(g.played_at, 1, 7) = ?
            GROUP BY gs.player_id
        ),
        adjustment_totals AS (
            SELECT
                player_id,
                SUM(score_change) AS adjustment_score
            FROM score_adjustments
            WHERE guild_id = ?
              AND substr(adjusted_at, 1, 7) = ?
            GROUP BY player_id
        ),
        all_players AS (
            SELECT player_id FROM game_totals
            UNION
            SELECT player_id FROM adjustment_totals
        )
        SELECT
            ap.player_id,
            COALESCE(gt.games_played, 0) AS games_played,
            COALESCE(gt.wins, 0) AS wins,
            COALESCE(gt.total_fan_won, 0) AS total_fan_won,
            COALESCE(gt.self_draw_wins, 0) AS self_draw_wins,
            COALESCE(gt.discard_losses, 0) AS discard_losses,
            COALESCE(gt.game_score, 0) + COALESCE(at.adjustment_score, 0) AS total_score,
            CASE
                WHEN COALESCE(gt.games_played, 0) = 0 THEN 0
                ELSE ROUND(100.0 * gt.wins / gt.games_played, 1)
            END AS win_rate
        FROM all_players ap
        LEFT JOIN game_totals gt ON gt.player_id = ap.player_id
        LEFT JOIN adjustment_totals at ON at.player_id = ap.player_id
        ORDER BY total_score DESC, wins DESC, total_fan_won DESC
    """, (
        str(guild_id),
        month,
        str(guild_id),
        month,
    ))

    rows = cur.fetchall()
    conn.close()

    return rows
