"""Re-run the train/validation/test study.

Requires data/btc_1m_long.pkl from scripts/build_data.py. This does not download
four years of bars unless you have already built that file. Results land in
data/ and are not a substitute for the committed study in research/results/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from scipy.stats import norm

from aroonbot.research import run_study
from aroonbot.study import bonferroni_z


def main() -> None:
    path = Path("data/btc_1m_long.pkl")
    if not path.exists():
        sys.exit("Missing data/btc_1m_long.pkl. Build it with scripts/build_data.py first.")
    frame = pd.read_pickle(path)
    results = run_study(frame)
    out = Path("data/research_results_rerun.csv")
    results.to_csv(out, index=False)
    n_variants = int((results.split == "val").sum())
    print("variants evaluated on validation:", n_variants)
    print("Bonferroni one-sided z for p=0.05:", round(bonferroni_z(n_variants), 2))
    print("norm check:", round(float(norm.ppf(1 - 0.05 / n_variants)), 2))
    chosen = results[results.split == "TEST_selected"]
    columns = ["H", "signal", "split", "trades", "hit", "z_vs_50", "pnl_sh_1c", "pnl_sh_3c"]
    print(chosen[columns].round(4).to_string(index=False))
    print("wrote", out)


if __name__ == "__main__":
    main()
