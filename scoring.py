FAN_SCORE_TABLE = {
    3: {"discard": 4, "self_draw_total": 6},
    4: {"discard": 8, "self_draw_total": 12},
    5: {"discard": 12, "self_draw_total": 18},
    6: {"discard": 16, "self_draw_total": 24},
    7: {"discard": 24, "self_draw_total": 36},
    8: {"discard": 32, "self_draw_total": 48},
    9: {"discard": 48, "self_draw_total": 72},
    10: {"discard": 64, "self_draw_total": 96},
    11: {"discard": 96, "self_draw_total": 144},
    12: {"discard": 128, "self_draw_total": 192},
    13: {"discard": 192, "self_draw_total": 288},
}


def calculate_score_changes(
    player_ids: list[int],
    winner_id: int,
    fan: int,
    win_type: str,
    loser_id: int | None = None,
) -> list[tuple[str, int]]:
    if fan not in FAN_SCORE_TABLE:
        raise ValueError("Fan must be between 3 and 13.")

    score_changes = []

    if win_type == "食糊":
        if loser_id is None:
            raise ValueError("Loser/discarder is required for 食糊.")

        base_score = FAN_SCORE_TABLE[fan]["discard"]

        for player_id in player_ids:
            if player_id == winner_id:
                score_change = base_score
            elif player_id == loser_id:
                score_change = -base_score
            else:
                score_change = 0

            score_changes.append((str(player_id), score_change))

    elif win_type == "自摸":
        self_draw_total = FAN_SCORE_TABLE[fan]["self_draw_total"]
        loss_per_player = self_draw_total // 3

        for player_id in player_ids:
            if player_id == winner_id:
                score_change = self_draw_total
            else:
                score_change = -loss_per_player

            score_changes.append((str(player_id), score_change))

    else:
        raise ValueError("Win type must be 自摸 or 食糊.")

    return score_changes
