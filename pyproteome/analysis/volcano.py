
from __future__ import absolute_import, division

import logging
import os
import re

from matplotlib import pyplot as plt
import numpy as np
import pandas as pd

import pyproteome as pyp


LOGGER = logging.getLogger("pyproteome.volcano")
MAX_VOLCANO_LABELS = 500


def _remove_lesser_dups(labels, compress_sym=False):
    labels["xy"] = labels.apply(lambda x: abs(x["x"]) + x["y"], axis=1)
    labels = labels.sort_values("xy", ascending=False)

    if compress_sym:
        labels = labels.drop_duplicates(subset="Label")
    else:
        labels = pd.concat([
            labels[labels["x"] >= 0].drop_duplicates(subset="Label"),
            labels[labels["x"] < 0].drop_duplicates(subset="Label"),
        ])

    return labels


def plot_volcano_labels(
    data,
    ax,
    upper_fold=None,
    lower_fold=None,
    p=None,
    fold_and_p=True,
    sequence_labels=False,
    options=None,
    show_duplicates=False,
    compress_sym=True,
    adjust=True,
    mods=None,
):
    """
    Plot labels on a volcano plot.
    """
    options = options or {}

    highlight = options.get('highlight', {})
    hide = options.get('hide', {})
    show = options.get('show', {})
    edgecolors = options.get('edgecolors', {})
    rename = options.get('rename', {})

    xminmax = ax.get_xlim()
    yminmax = ax.get_ylim()
    labels = []

    data.psms["x"] = data.psms["Fold Change"]
    data.psms["y"] = data.psms["p-value"]

    data.psms = data.psms[
        (data.psms["x"] >= xminmax[0]) &
        (data.psms["x"] <= xminmax[1]) &
        (data.psms["y"] >= yminmax[0]) &
        (data.psms["y"] <= yminmax[1])
    ]

    if sequence_labels:
        data.psms["Label"] = data.psms["Sequence"].apply(str)
    elif not mods:
        data.psms["Label"] = data.psms["Proteins"].apply(str)
    else:
        data.psms["Label"] = data.psms.apply(
            lambda x:
            " / ".join(
                [
                    "{} {}".format(
                        rename.get(gene, gene),
                        x["Modifications"].get_mods(
                            mods,
                        ).__str__(prot_index=index),
                    )
                    for index, gene in enumerate(x["Proteins"].genes)
                ]
            )
            if len(list(x["Modifications"].get_mods(mods))) > 0 else
            str(row["Proteins"]),
            axis=1,
        )

    def _get_names(row):
        names = [
            rename.get(row["Label"], row["Label"]),
            row["Label"],
        ]
        if "Sequence" in row:
            names += [str(row["Sequence"])]
        if "Proteins" in row:
            names += [
                j
                for i in row["Proteins"].genes
                for j in [i, rename.get(i, i)]
            ]

        return names

    data.psms["Names"] = data.psms.apply(_get_names, axis=1)

    data.psms = data.psms[
        data.psms["Names"].apply(lambda x: not any([i in hide for i in x]))
    ]
    data.psms = data.psms[
        data.psms["Names"].apply(lambda x: any([i in show for i in x])) | (
            (
                (data.psms["y"] >= p) &
                (
                    (data.psms["x"] >= upper_fold) |
                    (data.psms["x"] <= lower_fold)
                )
            )
            if fold_and_p else
            (
                (data.psms["y"] >= p) |
                (
                    (data.psms["x"] >= upper_fold) |
                    (data.psms["x"] <= lower_fold)
                )
            )
        )
    ]
    data.psms["Highlight"] = data.psms["Names"].apply(
        lambda x:
        any([
            i in highlight
            for i in x
        ])
    )
    data.psms["Label"] = data.psms["Names"].apply(
        lambda x:
        x[0]
    )

    def _get_txt_color(row):
        colors = [
            edgecolors.get(i)
            for i in row["Names"][:2]
            if i in edgecolors
        ]
        edgecolor = colors[0] if colors else None

        if edgecolor is None:
            gene_colors = [
                edgecolors.get(gene, None)
                for gene in row["Proteins"].genes
            ]
            if len(set(gene_colors)) == 1:
                edgecolor = gene_colors[0]

        return edgecolor

    data.psms["EdgeColor"] = data.psms.apply(
        _get_txt_color,
        axis=1,
    )

    labels = data.psms[
        [
            "x",
            "y",
            "Label",
            "EdgeColor",
            "Highlight",
        ]
    ].copy()

    if not show_duplicates:
        labels = _remove_lesser_dups(labels, compress_sym=compress_sym)

    # Position the labels
    texts = []
    txt_lim = 100 if mods else 11

    for _, row in labels.iterrows():
        texts.append(
            ax.text(
                x=row["x"],
                y=row["y"],
                s=row["Label"][:txt_lim] + (
                    "..." if len(row["Label"]) > txt_lim else ""
                ),
                zorder=10,
                fontsize=20 if row["Highlight"] else 16,
                horizontalalignment=(
                    'left' if row["x"] > 0 else "right"
                ),
                bbox=dict(
                    alpha=1,
                    linewidth=0.1,
                    pad=.2,
                    facecolor=row["EdgeColor"] or (
                        "#DDDDDD"
                        if edgecolors else
                        ("#BFEE90" if row["x"] > 0 else "#FFC1C1")
                    ),
                    zorder=1,
                    # edgecolor="black",
                    boxstyle="round",
                )
            )
        )

    if adjust:
        texts = texts[:MAX_VOLCANO_LABELS]
        pyp.utils.adjust_text(
            x=[i._x for i in texts],
            y=[i._y for i in texts],
            texts=texts,
            ax=ax,
            lim=100,
            force_text=0.5,
            force_points=0.01,
            arrowprops=dict(
                arrowstyle="->",
                relpos=(0, 0),
                lw=1,
                zorder=1,
                color="k",
            ),
            only_move={
                "points": "y",
                "text": "xy",
            }
        )

    LOGGER.info("Plotting volcano labels for {} peptides".format(len(texts)))

    return labels


def plot_volcano(
    data,
    group_a=None,
    group_b=None,
    p=0.05,
    fold=1.25,
    xminmax=None,
    yminmax=None,
    title=None,
    filename=None,
    folder_name=None,
    figsize=(12, 10),
    show_xlabel=True,
    show_ylabel=True,
    log2_fold=True,
    log10_p=True,
    bonferoni=False,
    **kwargs
):
    """
    Display a volcano plot of data.

    This plot inclues the fold-changes and p-values associated with said
    changes.

    Parameters
    ----------
    data : :class:`pyproteome.data_sets.DataSet`
    group_a : str or list of str, optional
    group_b : str or list of str, optional
    p : float, optional
    fold : float, optional
    folder_name : str, optional
    title : str, optional
    figsize : tuple of float, float
    kwargs : dict
        Arguments passed to :func:`.plot_volcano_labels`

    Returns
    -------
    f : :class:`matplotlib.figure.Figure`
    ax : :class:`matplotlib.axes.Axes`
    folder_name : str
    filename : str
    """
    data = data.copy()

    (channels_a, channels_b), (label_a, label_b), _ = data.get_groups(
        group_a=group_a,
        group_b=group_b,
    )

    if group_a and group_b:
        data.update_group_changes(group_a=group_a, group_b=group_b)

    folder_name = pyp.utils.make_folder(
        data=data,
        folder_name=folder_name,
        sub="Volcano",
    )

    if not filename:
        filename = re.sub("[ ></?]", "_", data.name) + ".png"

    if log10_p:
        p = -np.log10(p)
        data.psms["p-value"] = data.psms["p-value"].apply(
            lambda x: -np.log10(x)
        )

    if log2_fold:
        fold = np.log2(fold)
        data.psms["Fold Change"] = data.psms["Fold Change"].apply(
            lambda x: np.log2(x)
        )

    upper_fold = fold
    lower_fold = -upper_fold

    data.psms = data.psms.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["p-value", "Fold Change"],
        how="any",
    )

    if bonferoni:
        p += np.log10(data.shape[0])

    # Draw the figure
    fig, ax = plt.subplots(figsize=figsize)
    ax.scatter(
        data["Fold Change"],
        data["p-value"],
        s=5,
        c="grey",
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    if xminmax:
        ax.set_xlim(xmin=xminmax[0], xmax=xminmax[1])
    else:
        ax.set_xlim(
            xmin=np.floor(min(data["Fold Change"] + [0]) * 2) / 2,
            xmax=np.ceil(max(data["p-value"] + [0]) * 2) / 2,
        )

    if yminmax:
        ax.set_ylim(bottom=yminmax[0], top=yminmax[1])
    else:
        ax.set_ylim(bottom=-0.1)

    ax.set_xticks(
        list(
            sorted(
                tick
                for tick in ax.get_xticks()
                if tick < lower_fold - .25 or tick > upper_fold + .25
            ) + [lower_fold, upper_fold]
        )
    )
    ax.set_yticks(
        list(
            sorted(
                [
                    tick
                    for tick in ax.get_yticks()
                    if "{}".format(np.power(1/10, tick)).strip("0.")[:1] in
                    ["1", "5"] and
                    tick > p
                ] + [p]
            )
        )
    )

    ax.set_xticklabels(
        [
            "{:.3}".format(np.exp2(i) if log2_fold else i)
            for i in ax.get_xticks()
        ],
    )
    ax.set_yticklabels(
        [
            (
                "{:.3}" if i > 5e-3 else "{:.0e}"
            ).format(np.power(1/10, i) if log10_p else i)
            for i in ax.get_yticks()
        ],
    )

    if show_xlabel:
        max_len = 25
        ax.set_xlabel(
            "{} (n={}) / {} (n={})".format(
                label_a[:max_len] + ("..." if len(label_a) > max_len else ""),
                len(channels_a),
                label_b[:max_len] + ("..." if len(label_b) > max_len else ""),
                len(channels_b),
            ),
        )

    if show_ylabel:
        ax.set_ylabel(
            "p-value",
        )

    if not np.isnan(p):
        ax.axhline(
            p,
            color="r", linestyle="dashed", linewidth=0.5,
        )

    if abs(fold - 1) > 0.01:
        ax.axvline(upper_fold, color="r", linestyle="dashed", linewidth=0.5)
        ax.axvline(lower_fold, color="r", linestyle="dashed", linewidth=0.5)

    if title:
        ax.set_title(
            title,
        )

    plot_volcano_labels(
        data=data,
        ax=ax,
        upper_fold=upper_fold,
        lower_fold=lower_fold,
        p=p,
        **kwargs
    )

    if filename:
        fig.savefig(
            os.path.join(folder_name, filename),
            bbox_inches="tight",
            dpi=pyp.DEFAULT_DPI,
            transparent=True,
        )

    return fig, ax, folder_name, filename


def plot_volcano_filtered(data, f, **kwargs):
    """
    Display a volcano plot, showing only peptides that are included by a given
    filter.

    All extra arguments will be passed directly to `plot_volcano`.

    Parameters
    ----------
    data : :class:`pyproteome.data_sets.DataSet`
    f : dict or list of dict
        Filters passed to data.filter().

    Returns
    -------
    f : :class:`matplotlib.figure.Figure`
    ax : :class:`matplotlib.axes.Axes`
    """
    data = data.copy()
    data.update_group_changes(
        group_a=kwargs.get("group_a", None),
        group_b=kwargs.get("group_b", None),
    )

    d = data.filter(f)

    changes = []
    pvals = []

    for _, row in data.psms.iterrows():
        row_pval = -np.log10(row["p-value"])
        row_change = np.log2(row["Fold Change"])

        if (
            np.isnan(row_pval) or
            np.isnan(row_change) or
            np.isinf(row_pval) or
            np.isinf(row_change)
        ):
            continue

        pvals.append(row_pval)
        changes.append(row_change)

    xminmax = kwargs.pop(
        "xminmax",
        (
            np.floor(min(changes + [0]) * 2) / 2,
            np.ceil(max(changes + [0]) * 2) / 2,
        ),
    )
    yminmax = kwargs.pop(
        "yminmax",
        (-0.1, np.ceil(max(pvals + [1]))),
    )

    f, ax, folder_name, filename = plot_volcano(
        d,
        xminmax=xminmax,
        yminmax=yminmax,
        **kwargs
    )

    if changes and pvals:
        changes, pvals = zip(*[
            (x, y)
            for x, y in zip(changes, pvals)
            if x > xminmax[0] and x < xminmax[1] and
            y > yminmax[0] and y < yminmax[1]
        ])

    ax.scatter(
        changes,
        pvals,
        s=5,
        zorder=0,
        c="grey",
        # c="lightblue",
        # alpha=0.3,
    )

    if filename:
        f.savefig(
            os.path.join(folder_name, filename),
            bbox_inches="tight",
            dpi=pyp.DEFAULT_DPI,
            transparent=True,
        )

    return f, ax
