
from io import BytesIO
import gzip
import os
import requests

import numpy as np
import pandas as pd

import pyproteome as pyp
from . import motif, logo


DATA_URL = "https://www.phosphosite.org/downloads/Kinase_Substrate_Dataset.gz"


@pyp.utils.memoize
def get_data():
    data = requests.get(DATA_URL, stream=True)
    content = BytesIO(data.content)

    with gzip.GzipFile(fileobj=content) as f:
        df = pd.read_csv(f, skiprows=range(2), sep="\t")

    return df


def generate_logos(species, kinases=None, folder_name=None, min_foreground=10):
    folder_name = pyp.utils.make_folder(
        folder_name=folder_name,
        sub="Logos",
    )

    df = get_data()
    df = df[
        np.logical_and(
            df["KIN_ORGANISM"] == species,
            df["SUB_ORGANISM"] == species,
        )
    ]

    if kinases is None:
        kinases = kinases = sorted(set(df["KINASE"]))

    for kinase in kinases:
        fore = list(df[df["KINASE"] == kinase]["SITE_+/-7_AA"])

        if len(fore) < min_foreground:
            continue

        f = logo.logo(
            fore=fore,
            back=list(df["SITE_+/-7_AA"]),
            title=kinase,
        )[0]
        f.savefig(
            os.path.join(folder_name, "{}.png".format(kinase)),
            dpi=f.dpi,
            bbox_inches="tight",
            pad_inches=.1,
        )


def enriched(data, species=None):
    df = get_data()

    if species:
        df = df[
            np.logical_and(
                df["KIN_ORGANISM"] == species,
                df["SUB_ORGANISM"] == species,
            )
        ]

    return df[
        df["SITE_+/-7_AA"].isin(
            motif.generate_n_mers(
                data["Sequence"],
                fill_left="_",
                fill_right="_",
                letter_mod_types=[(None, "Phospho")],
            )
        )
    ].style.set_table_styles(
        [
            {"selector": "th:first-child", "props": [("display", "none")]},
        ]
    )
