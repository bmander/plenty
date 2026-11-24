"""Draw figures/*.png from results/*.csv."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flourishing import model as M

RES, FIG = M.ROOT / "results", M.ROOT / "figures"
SURFACE, INK, INK2, GRID, BLUE = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "text.color": INK,
                     "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "savefig.facecolor": SURFACE})
HAS_BOARD = {"cad", "fea", "cam", "pcb"}
LABEL = {"cad": "CAD / B-rep", "fea": "FEA", "cfd": "CFD / heat transfer", "cam": "CAM",
         "mfgsim": "Mfg process simulation", "mbd": "Multibody dynamics", "emag": "EM field",
         "pcb": "PCB design", "ic": "IC design", "controls": "Controls / PLC / dynamics",
         "process": "Process flowsheeting", "power": "Power systems", "civil": "Civil / structural / BIM",
         "hydraulics": "Pipe-network hydraulics", "molecular": "Molecular / bio modeling",
         "logistics": "Logistics optimization", "gis": "Geospatial", "firmware": "Embedded toolchains"}


def clean(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def capabilities():
    c = pd.read_csv(RES / "capability_table.csv", index_col=0).sort_values("volume weight")
    names = [LABEL[k] + ("  ●" if k in HAS_BOARD else "") for k in c.index]
    fig, axes = plt.subplots(1, 2, figsize=(11, 6.2), sharey=True)
    panels = [("volume weight", "Volume weight", "score-weighted share of the basket's embodied value added"),
              ("exposure", "Exposure", "\\$ of output from capability-critical sectors per \\$ of basket")]
    for ax, (col, title, sub) in zip(axes, panels):
        ax.barh(names, c[col], height=0.62, color=BLUE)
        for y, v in enumerate(c[col]):
            ax.text(v + c[col].max() * 0.012, y, f"{v:.2f}" if v >= 0.1 else f"{v:.3f}", va="center", fontsize=8.5, color=INK2)
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=22)
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=8.5, color=INK2)
        ax.set_xlim(0, c[col].max() * 1.13)
        clean(ax)
    fig.suptitle("Engineering capabilities on the path to the flourishing basket", x=0.012, ha="left", fontsize=13.5, fontweight="bold")
    fig.text(0.012, 0.012, "● has an open leaderboard today.   Sorted by volume weight; both panels share the row order.   "
             "Capability scores are elicited, not measured (config/archetype_capabilities.csv).", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0.035, 1, 0.95))
    fig.savefig(FIG / "capabilities.png", dpi=160)


def sectors():
    s = pd.read_csv(RES / "sectors.csv", index_col=0)
    phys = s[s.index.isin(pd.read_csv(RES / "physical_sectors.csv", index_col=0).index)]
    fig, ax = plt.subplots(figsize=(11, 6.6))
    ax.scatter(phys.output_per_basket_dollar, phys.need_breadth_observed, s=26, color=BLUE, alpha=0.5,
               edgecolor=SURFACE, linewidth=0.8)
    ax.set_xscale("log")
    picks = {  # code: (label, x offset, y offset) in points
        "221100": ("Electric power", -30, -14), "211000": ("Oil and gas extraction", -40, 9),
        "331110": ("Iron and steel", 7, 3), "325412": ("Pharmaceuticals", -62, 11),
        "233411": ("Single-family houses", -62, -16), "333914": ("Pumps", 8, 6),
        "335314": ("Relays and industrial controls", -168, 4), "333517": ("Machine tools", -84, -4),
        "334413": ("Semiconductors", 7, -11), "332991": ("Bearings", -52, -3),
        "325310": ("Fertilizer", 7, -4), 
        "1111B0": ("Grain farming", 7, -3),
        "333912": ("Compressors", -62, 9), "336411": ("Aircraft", 7, -3),
        "333111": ("Farm machinery", 7, -3),
    }
    for code, (lab, dx, dy) in picks.items():
        x, y = phys.at[code, "output_per_basket_dollar"], phys.at[code, "need_breadth_observed"]
        ax.scatter([x], [y], s=36, color=BLUE, edgecolor=INK, linewidth=0.9, zorder=3)
        ax.annotate(lab, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=8.5, color=INK)
    ax.set_xlabel("Volume: \\$ of sector output per \\$ of basket (log scale)")
    ax.set_ylabel("Breadth: effective number of needs served (of 11), observed purchases", color=INK2)
    ax.set_ylim(0.5, 11.5)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(True, color=GRID, linewidth=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
    ax.set_title("Physical sectors on the basket path: volume vs. breadth",
                 loc="left", fontsize=12.5, fontweight="bold", pad=12)
    fig.text(0.012, 0.012, f"{len(phys)} farming, extraction, utility, construction and manufacturing sectors "
             "(BEA 2017 detail). Upper left = small but needed by nearly everything.", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    fig.savefig(FIG / "sectors.png", dpi=160)


if __name__ == "__main__":
    capabilities()
    sectors()
