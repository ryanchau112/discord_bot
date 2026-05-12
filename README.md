# Hong Kong Mahjong Discord Bot

A Discord bot for recording Hong Kong Mahjong games, calculating scores, and showing a monthly leaderboard.

## Features

- Start a Mahjong table with 4 players
- Record wins by `自摸` or `食糊`
- Score calculation based on a Hong Kong Mahjong fan-to-score table
- Monthly leaderboard by net score
- Count wins, self-draw wins, and discard losses
- Backfill previous games
- Undo the latest game record
- Manual score adjustments
- SQLite database

## Scoring rules

| Fan | Discard win score | Self-draw score total |
|---:|---:|---:|
| 3 | 4 | 6 |
| 4 | 8 | 12 |
| 5 | 12 | 18 |
| 6 | 16 | 24 |
| 7 | 24 | 36 |
| 8 | 32 | 48 |
| 9 | 48 | 72 |
| 10 | 64 | 96 |
| 11 | 96 | 144 |
| 12 | 128 | 192 |
| 13 | 192 | 288 |

For `食糊`, only the discarder loses the discard win score and the winner gains that score.

For `自摸`, the self-draw score is the **total** score gained by the winner. The three other players share that loss equally.

Example:

```text
5 fan 自摸 = 18 total
Winner: +18
Each other player: -6
```

## Setup

Create a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
nano .env
```

Add your Discord bot token:

```env
DISCORD_TOKEN=your_discord_bot_token_here
```

Run the bot:

```bash
python bot.py
```

## Commands

### Start a table

```text
/start_table
```

Select East, South, West, and North players.

### Record a win

```text
/win
```

For `食糊`, select the winner, fan, win type, and discarder.

For `自摸`, select the winner, fan, and win type. Leave loser empty.

### Show current table

```text
/table
```

### Show leaderboard

```text
/leaderboard
```

Optional month format:

```text
2026-05
```

### Backfill an old game

```text
/backfill_game
```

Use date format:

```text
YYYY-MM-DD HH:MM
```

### Undo latest game

```text
/undo_game
```

### Manually adjust score

```text
/adjust_score
```

### End table

```text
/end_table
```

## Notes

The bot stores data in `mahjong.db`. This file is ignored by Git and should be backed up separately.

Never commit your real `.env` file or Discord token.
