import math

from aroonbot.study import bonferroni_z, leaderboard, primary_pm, study_summary


def test_committed_study_selection_and_z():
    board = leaderboard()
    assert board["n_validation_variants"] == 81
    assert round(board["bonferroni_z"], 2) == 3.23
    assert math.isclose(board["bonferroni_z"], bonferroni_z(81))
    selected = {row["minutes"]: row for row in board["selected"]}
    assert set(selected) == {5, 15, 60}
    for row in selected.values():
        assert row["signal"] == "rsi_mr_30_70"
        recomputed = (row["hit"] - 0.5) / math.sqrt(0.25 / row["trades"])
        assert math.isclose(recomputed, row["z_vs_50"], rel_tol=1e-9)
    assert selected[5]["passes_bonferroni"]
    assert selected[15]["passes_bonferroni"]
    assert not selected[60]["passes_bonferroni"]
    assert selected[15]["hit"] > 0.55
    assert selected[15]["trades"] == 2415


def test_polymarket_check_is_negative_after_fees():
    prices = {row["minutes"]: row for row in primary_pm()}
    assert set(prices) == {5, 15, 60}
    for row in prices.values():
        assert row["avg_pnl_per_share"] < 0
        assert row["avg_cost"] > 0.5
    assert prices[15]["n_fire"] == 2409
    summary = study_summary()
    assert "loses money" in summary["headline"] or "negative" in summary["headline"]
    assert summary["paper_only"] is True
    joined = " ".join(summary["sentences"])
    assert "rsi_mr_30_70" in joined
    assert "15m" in joined
