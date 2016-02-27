"""
This module provides functionality for interpreting BCA assays.
"""

# Built-ins
from collections import defaultdict
import logging
import os
import re

# Core data analysis libraries
import numpy as np
import pandas as pd
from scipy.stats import linregress

from IPython.display import display

LOGGER = logging.getLogger("pyproteome.bca")
RE_ROW_COL = re.compile("([A-Z]+)(\d+)")


def _interpret_pos(pos):
    """
    Turn a position (i.e. "A1:B2") into integers for the row / column range.

    Parameters
    ----------
    pos : str

    Returns
    -------
    col_start : int
    col_end : int
    row_start : int
    row_end : int
    """
    lst = pos.split(":")

    m = RE_ROW_COL.match(lst[0])
    row_start, col_start = m.groups()
    col_start = int(col_start)

    if len(lst) > 1:
        m = RE_ROW_COL.match(lst[1])
        row_end, col_end = m.groups()
        col_end = int(col_end)
    else:
        row_end, col_end = None, None

    return col_start, col_end, row_start, row_end


def _next_chr(char):
    return chr(ord(char) + 1)


def interpret_bca_assay(
    xls_path,
    samples,
    volumes,
    standards=None,
    n=3,
    data_row_start=27,
):
    """
    Load and interpret a plate reader output.

    Fits a curve to the standards, checks data sanity, and calculates sample
    concentrations.

    Parameters
    ----------
    xls_path : str
        Path to output of Tecan reader.
    samples : list of tuple of (str, float, str)
        Sample names, dilutions, and positions within the plate. Positions
        should be supplied as either the left index of the first of three
        aliquots (i.e. "A4") or a range indicating the starting and ending row
        and column (i.e. "A4:B6").
    volumes : dict of str, float
        Volumes of samples, in μL.
    standards : list of (tuple of int, float), optional
        Locations of standards in table. Defaults to the first n (below)
        columns, rows A-G, with concentrations 1 - 0.0625 mg / mL, followed by
        two blanks of PBS.
    n : int, optional
        Number of replicates to use for standards and samples (Defaults to 3).
    data_row_start : int, optional
        Starting row in excel file for absorbance table.

    Returns
    -------
    total_protein : dict of str, tuple of (float, float)
        Sample total protein contents. Supplies the mean and standard deviation
        for the calculated protein content (in μg)
    concentrations : dict of list of float
        Individual concentrations calculations.

    Raises
    ------

    Examples
    --------
    >>> from pyproteome import bca
    >>> total_protein, _ = bca.interpret_bca_assay(
    ...     "bsa-sample.xlsx",
    ...     samples=[
    ...         ("3157 Hippocampus", 10, "A4:B6"),
    ...         ("3157 Cortex", 10, "C4:D6"),
    ...         ("3146 Cerebellum", 10, "E4:F6"),
    ...         ("3146 Hippocampus", 10, "G4:H6"),
    ...     ],
    ...     volumes={
    ...         "3157 Hippocampus": 3000,
    ...         "3157 Cortex": 3000,
    ...         "3146 Cerebellum": 3000,
    ...         "3146 Hippocampus": 3000,
    ...     },
    ... )
    >>> cortex = total_protein["3157 Cortex"]
    >>> print("{:.2f} +/- {:.2f} ug".format(cortex[0], cortex[1])
    8094.51 +/- 340.66 ug
    """

    xls = pd.read_excel(
        xls_path,
        skiprows=(
            list(range(data_row_start)) +
            list(range(data_row_start + 9, data_row_start + 13))
        ),
        index_col=0,
    )

    if isinstance(xls, dict):
        assert len(xls) == 1
        xls = list(xls.values())[0]

    # Drop columns with NaN values
    xls = xls.dropna(
        axis=1,
        how="any",
    )

    std_start_col = xls.columns[0]

    if standards is None:
        standards = [
            ("A{}".format(std_start_col), 1.0),
            ("B{}".format(std_start_col), 0.5),
            ("C{}".format(std_start_col), 0.25),
            ("D{}".format(std_start_col), 0.125),
            ("E{}".format(std_start_col), 0.0625),
            ("F{}".format(std_start_col), 0),
            ("G{}".format(std_start_col), 0),
        ]

    # Extract out standards absorbances
    std_x = []
    std_y = []

    for pos, x in standards:
        col_start, col_end, row_start, row_end = _interpret_pos(pos)

        if col_end is None:
            col_end = col_start + 3

        if row_end is None:
            row_end = row_start

        row = row_start

        while row <= row_end:
            for col in range(std_start_col, std_start_col + 3):
                std_x.append(x)
                std_y.append(xls.ix[row][col])

            row = _next_chr(row)

    # Fit a linear regression model to standards
    slope, intercept, r, _, _ = linregress(std_x, std_y)

    # Sanity check standards
    if r ** 2 < 0.95:
        raise Exception("R^2 of standards = {:.2f} (< 0.95)".format(r ** 2))

    # Extract out sample absorbances and concentrations
    absorbances = defaultdict(list)
    concentrations = defaultdict(list)
    total_protein = {}

    for name, dilution, pos in samples:
        col_start, col_end, row_start, row_end = _interpret_pos(pos)

        if col_end is None:
            col_end = col_start + 3

        if row_end is None:
            row_end = row_start

        row = row_start

        while row <= row_end:
            for col in range(col_start, col_end + 1):
                absorbance = xls.ix[row][col]
                concentration = (absorbance - intercept) / slope
                concentrations[name].append(concentration * dilution)
                absorbances[name].append(absorbance)

            row = _next_chr(row)

    # Sanity check concentrations

    # Calculate total sample protein content
    for name, volume in volumes.items():
        protein = np.array(concentrations[name]) * volume
        total_protein[name] = (
            protein.mean(),
            protein.std(),
        )

    return total_protein, concentrations
