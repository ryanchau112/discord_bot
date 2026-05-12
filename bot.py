import os
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from database import (
    init_db,
    get_active_session,
    get_session_players,
    create_session,
    insert_game,
    insert_game_with_played_at,
    get_latest_game_for_session,
    delete_game,
    end_session,
    get_monthly_leaderboard,
    add_score_adjustment,
)

from scoring import calculate_score_changes, FAN_SCORE_TABLE


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

NAME_CACHE = {}
NAME_CACHE_SECONDS = 600


async def get_player_name(guild: discord.Guild | None, player_id: str) -> str:
    if guild is None:
        return f"User {player_id}"

    cache_key = (guild.id, str(player_id))
    now = datetime.now(timezone.utc)

    cached = NAME_CACHE.get(cache_key)
    if cached:
        cached_name, cached_at = cached
        if now - cached_at < timedelta(seconds=NAME_CACHE_SECONDS):
            return cached_name

    member = guild.get_member(int(player_id))
    if member:
        NAME_CACHE[cache_key] = (member.display_name, now)
        return member.display_name

    try:
        member = await guild.fetch_member(int(player_id))
        NAME_CACHE[cache_key] = (member.display_name, now)
        return member.display_name
    except discord.NotFound:
        return f"Unknown User {player_id}"
    except discord.HTTPException:
        return f"User {player_id}"


def validate_loser(
    loser: discord.Member | None,
    winner: discord.Member,
    player_ids: list[int],
) -> str | None:
    if loser is None:
        return None

    if loser.id not in player_ids:
        return "Loser must be one of the current table players."

    if loser.id == winner.id:
        return "Winner and loser cannot be the same person."

    return None


@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


@bot.tree.command(name="start_table", description="Start a Hong Kong Mahjong table")
@app_commands.describe(
    east="East player",
    south="South player",
    west="West player",
    north="North player",
)
async def start_table(
    interaction: discord.Interaction,
    east: discord.Member,
    south: discord.Member,
    west: discord.Member,
    north: discord.Member,
):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    players = [east, south, west, north]

    if len(set(player.id for player in players)) != 4:
        await interaction.response.send_message(
            "Please choose 4 different players.",
            ephemeral=True,
        )
        return

    existing_session = get_active_session(
        interaction.guild_id,
        interaction.channel_id,
    )

    if existing_session:
        await interaction.response.send_message(
            "There is already an active Mahjong table in this channel. Use /end_table first.",
            ephemeral=True,
        )
        return

    create_session(
        guild_id=interaction.guild_id,
        channel_id=interaction.channel_id,
        players=[
            ("East", east.id),
            ("South", south.id),
            ("West", west.id),
            ("North", north.id),
        ],
    )

    await interaction.response.send_message(
        f"🀄 Mahjong table started.\n\n"
        f"East: {east.display_name}\n"
        f"South: {south.display_name}\n"
        f"West: {west.display_name}\n"
        f"North: {north.display_name}\n\n"
        f"Use `/win` to record each game."
    )


@bot.tree.command(name="table", description="Show the active Mahjong table")
async def table(interaction: discord.Interaction):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    session_id = get_active_session(
        interaction.guild_id,
        interaction.channel_id,
    )

    if not session_id:
        await interaction.response.send_message(
            "No active Mahjong table in this channel.",
            ephemeral=True,
        )
        return

    players = get_session_players(session_id)

    lines = ["🀄 Current Mahjong Table\n"]

    for player_id, seat in players:
        player_name = await get_player_name(interaction.guild, player_id)
        lines.append(f"{seat}: {player_name}")

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="win", description="Record a Mahjong win for the active table")
@app_commands.describe(
    winner="Who won?",
    fan="How many fan? 3 to 13",
    win_type="自摸 or 食糊",
    loser="For 食糊: discarder. For 自摸: optional 包自摸 payer.",
    notes="Optional hand description, e.g. 混一色, 對對糊",
)
@app_commands.choices(
    win_type=[
        app_commands.Choice(name="自摸", value="自摸"),
        app_commands.Choice(name="食糊", value="食糊"),
    ]
)
async def win(
    interaction: discord.Interaction,
    winner: discord.Member,
    fan: int,
    win_type: app_commands.Choice[str],
    loser: discord.Member | None = None,
    notes: str | None = None,
):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    if fan not in FAN_SCORE_TABLE:
        await interaction.response.send_message(
            "Fan must be between 3 and 13.",
            ephemeral=True,
        )
        return

    session_id = get_active_session(
        interaction.guild_id,
        interaction.channel_id,
    )

    if not session_id:
        await interaction.response.send_message(
            "No active Mahjong table in this channel. Use `/start_table` first.",
            ephemeral=True,
        )
        return

    session_players = get_session_players(session_id)
    player_ids = [int(player_id) for player_id, _seat in session_players]

    if winner.id not in player_ids:
        await interaction.response.send_message(
            "Winner must be one of the current table players.",
            ephemeral=True,
        )
        return

    loser_id = None

    if win_type.value == "食糊" and loser is None:
        await interaction.response.send_message(
            "For 食糊, please select the discarder.",
            ephemeral=True,
        )
        return

    validation_error = validate_loser(loser, winner, player_ids)
    if validation_error:
        await interaction.response.send_message(
            validation_error,
            ephemeral=True,
        )
        return

    if loser is not None:
        loser_id = loser.id

    try:
        score_changes = calculate_score_changes(
            player_ids=player_ids,
            winner_id=winner.id,
            fan=fan,
            win_type=win_type.value,
            loser_id=loser_id,
        )
    except ValueError as error:
        await interaction.response.send_message(
            str(error),
            ephemeral=True,
        )
        return

    game_id = insert_game(
        session_id=session_id,
        winner_id=winner.id,
        fan=fan,
        win_type=win_type.value,
        loser_id=loser_id,
        notes=notes,
        score_changes=score_changes,
    )

    score_lines = []
    for player_id, score_change in score_changes:
        sign = "+" if score_change > 0 else ""
        player_name = await get_player_name(interaction.guild, player_id)
        score_lines.append(f"{player_name}: {sign}{score_change}")

    notes_text = f"\nNotes: {notes}" if notes else ""
    bao_text = "\n包自摸: Yes" if win_type.value == "自摸" and loser_id else ""

    await interaction.response.send_message(
        f"✅ Game #{game_id} recorded.\n\n"
        f"Winner: {winner.display_name}\n"
        f"Fan: {fan}\n"
        f"Win type: {win_type.value}"
        f"{bao_text}"
        f"{notes_text}\n\n"
        f"Score changes:\n"
        + "\n".join(score_lines)
    )


@bot.tree.command(name="backfill_game", description="Insert a previous Mahjong game into the active table")
@app_commands.describe(
    played_at="Date/time of the game, e.g. 2026-05-01 20:15",
    winner="Who won?",
    fan="How many fan? 3 to 13",
    win_type="自摸 or 食糊",
    loser="For 食糊: discarder. For 自摸: optional 包自摸 payer.",
    notes="Optional hand description",
)
@app_commands.choices(
    win_type=[
        app_commands.Choice(name="自摸", value="自摸"),
        app_commands.Choice(name="食糊", value="食糊"),
    ]
)
async def backfill_game(
    interaction: discord.Interaction,
    played_at: str,
    winner: discord.Member,
    fan: int,
    win_type: app_commands.Choice[str],
    loser: discord.Member | None = None,
    notes: str | None = None,
):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    if fan not in FAN_SCORE_TABLE:
        await interaction.response.send_message(
            "Fan must be between 3 and 13.",
            ephemeral=True,
        )
        return

    try:
        parsed_date = datetime.strptime(played_at, "%Y-%m-%d %H:%M")
        played_at_value = parsed_date.isoformat()
    except ValueError:
        await interaction.response.send_message(
            "Invalid date format. Use `YYYY-MM-DD HH:MM`, e.g. `2026-05-01 20:15`.",
            ephemeral=True,
        )
        return

    session_id = get_active_session(
        interaction.guild_id,
        interaction.channel_id,
    )

    if not session_id:
        await interaction.response.send_message(
            "No active Mahjong table in this channel. Use `/start_table` first.",
            ephemeral=True,
        )
        return

    session_players = get_session_players(session_id)
    player_ids = [int(player_id) for player_id, _seat in session_players]

    if winner.id not in player_ids:
        await interaction.response.send_message(
            "Winner must be one of the current table players.",
            ephemeral=True,
        )
        return

    loser_id = None

    if win_type.value == "食糊" and loser is None:
        await interaction.response.send_message(
            "For 食糊, please select the discarder.",
            ephemeral=True,
        )
        return

    validation_error = validate_loser(loser, winner, player_ids)
    if validation_error:
        await interaction.response.send_message(
            validation_error,
            ephemeral=True,
        )
        return

    if loser is not None:
        loser_id = loser.id

    try:
        score_changes = calculate_score_changes(
            player_ids=player_ids,
            winner_id=winner.id,
            fan=fan,
            win_type=win_type.value,
            loser_id=loser_id,
        )
    except ValueError as error:
        await interaction.response.send_message(
            str(error),
            ephemeral=True,
        )
        return

    game_id = insert_game_with_played_at(
        session_id=session_id,
        played_at=played_at_value,
        winner_id=winner.id,
        fan=fan,
        win_type=win_type.value,
        loser_id=loser_id,
        notes=notes,
        score_changes=score_changes,
    )

    score_lines = []
    for player_id, score_change in score_changes:
        sign = "+" if score_change > 0 else ""
        player_name = await get_player_name(interaction.guild, player_id)
        score_lines.append(f"{player_name}: {sign}{score_change}")

    bao_text = "\n包自摸: Yes" if win_type.value == "自摸" and loser_id else ""

    await interaction.response.send_message(
        f"✅ Previous game #{game_id} inserted.\n\n"
        f"Played at: {played_at}\n"
        f"Winner: {winner.display_name}\n"
        f"Fan: {fan}\n"
        f"Win type: {win_type.value}"
        f"{bao_text}\n\n"
        f"Score changes:\n"
        + "\n".join(score_lines)
    )


@bot.tree.command(name="undo_game", description="Undo the latest Mahjong game record in this channel")
async def undo_game(interaction: discord.Interaction):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    session_id = get_active_session(
        interaction.guild_id,
        interaction.channel_id,
    )

    if not session_id:
        await interaction.response.send_message(
            "No active Mahjong table in this channel.",
            ephemeral=True,
        )
        return

    latest_game = get_latest_game_for_session(session_id)

    if not latest_game:
        await interaction.response.send_message(
            "There is no game record to undo for this table.",
            ephemeral=True,
        )
        return

    game_id, winner_id, fan, win_type, loser_id, notes, played_at = latest_game

    delete_game(game_id)

    winner_name = await get_player_name(interaction.guild, winner_id)

    loser_text = ""
    if loser_id:
        loser_name = await get_player_name(interaction.guild, loser_id)
        loser_label = "包自摸 payer" if win_type == "自摸" else "Discarder"
        loser_text = f"\n{loser_label}: {loser_name}"

    notes_text = f"\nNotes: {notes}" if notes else ""

    await interaction.response.send_message(
        f"↩️ Latest game record has been undone.\n\n"
        f"Deleted game #{game_id}\n"
        f"Winner: {winner_name}\n"
        f"Fan: {fan}\n"
        f"Win type: {win_type}"
        f"{loser_text}"
        f"{notes_text}"
    )


@bot.tree.command(name="adjust_score", description="Manually adjust a player's leaderboard score")
@app_commands.describe(
    player="Player to adjust",
    score_change="Score change, e.g. 20 or -20",
    reason="Reason for the adjustment",
)
async def adjust_score(
    interaction: discord.Interaction,
    player: discord.Member,
    score_change: int,
    reason: str | None = None,
):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    add_score_adjustment(
        guild_id=interaction.guild_id,
        player_id=player.id,
        score_change=score_change,
        reason=reason,
    )

    sign = "+" if score_change > 0 else ""

    await interaction.response.send_message(
        f"✅ Score adjusted.\n\n"
        f"Player: {player.display_name}\n"
        f"Change: {sign}{score_change}\n"
        f"Reason: {reason or 'No reason provided'}"
    )


@bot.tree.command(name="leaderboard", description="Show monthly Mahjong leaderboard")
@app_commands.describe(
    month="Month in YYYY-MM format, e.g. 2026-05. Leave empty for current month.",
)
async def leaderboard(
    interaction: discord.Interaction,
    month: str | None = None,
):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    if month is None:
        month = datetime.now(timezone.utc).strftime("%Y-%m")

    rows = get_monthly_leaderboard(
        guild_id=interaction.guild_id,
        month=month,
    )

    if not rows:
        await interaction.response.send_message(
            f"No games recorded for {month}."
        )
        return

    lines = [f"🏆 Mahjong Leaderboard - {month}\n"]

    for index, row in enumerate(rows, start=1):
        (
            player_id,
            games_played,
            wins,
            _total_fan_won,
            self_draw_wins,
            discard_losses,
            total_score,
            win_rate,
        ) = row

        sign = "+" if total_score and total_score > 0 else ""
        player_name = await get_player_name(interaction.guild, player_id)

        lines.append(
            f"{index}. {player_name}: "
            f"{sign}{total_score or 0} net score | "
            f"{wins or 0} wins | "
            f"自摸 {self_draw_wins or 0} | "
            f"放銃 {discard_losses or 0} | "
            f"{games_played} games | "
            f"{win_rate or 0}% win rate"
        )

    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="end_table", description="End the active Mahjong table")
async def end_table_command(interaction: discord.Interaction):
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    session_id = get_active_session(
        interaction.guild_id,
        interaction.channel_id,
    )

    if not session_id:
        await interaction.response.send_message(
            "No active Mahjong table to end.",
            ephemeral=True,
        )
        return

    end_session(session_id)

    await interaction.response.send_message("🛑 Mahjong table ended.")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env file.")

bot.run(TOKEN)
