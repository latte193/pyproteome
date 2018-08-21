# -*- coding: UTF-8 -*-
"""
This module provides functionality for signal pathway analysis.

It includes functions for Gene Set Enrichment Analysis (GSEA) as well as
Phospho Set Enrichment Analysis (PSEA).
"""

from __future__ import absolute_import, division

import logging
import os

import numpy as np
import pandas as pd


import pyproteome as pyp
import brainrnaseq as brs
from . import enrichments, msigdb, psp, wikipathways, photon_ptm


LOGGER = logging.getLogger("pyproteome.pathways")


def _remap_data(psms, from_species, to_species):
    new = psms.copy()

    from_species = pyp.species.ORGANISM_MAPPING.get(from_species, from_species)
    to_species = pyp.species.ORGANISM_MAPPING.get(to_species, to_species)

    LOGGER.info(
        "Remapping phosphosites from {} to {}".format(from_species, to_species)
    )

    mapping = psp.get_phosphomap_data()
    mapping = mapping[["ACC_ID", "MOD_RSD", "ORGANISM", "SITE_GRP_ID"]]

    acc_mapping = mapping[
        mapping["ORGANISM"] == from_species
    ].set_index(
        ["ACC_ID", "MOD_RSD"]
    ).sort_index()
    site_mapping = mapping[
        mapping["ORGANISM"] == to_species
    ].set_index(
        ["SITE_GRP_ID"]
    ).sort_index()

    del mapping

    def _remap(val):
        acc, mod = val.split(",")

        try:
            site = acc_mapping.loc[acc, mod]
        except KeyError:
            return None

        site = site.iloc[0]["SITE_GRP_ID"]

        try:
            re_map = site_mapping.loc[site]
        except KeyError:
            return None

        if len(re_map.shape) > 1:
            re_map = re_map.iloc[0]

        acc = re_map["ACC_ID"]
        mod = re_map["MOD_RSD"]
        return ",".join([acc, mod])

    new["ID"] = new["ID"].apply(_remap)
    new = new[~(new["ID"].isnull())]

    LOGGER.info(
        "Mapping {} IDs ({}) down to {} IDs ({})"
        .format(psms.shape[0], from_species, new.shape[0], to_species)
    )

    return new


def _get_psite_ids(ds, species):
    LOGGER.info("Building list of individual phosphosites")
    new_rows = []

    def _split_rows(row):
        mods = row["Modifications"].get_mods("Phospho")

        # Generate rows for each phosphosite on a peptide mapped to each
        # possible protein for ambiguous peptides.
        for mod in mods:
            for gene, abs_pos in zip(row["Proteins"].accessions, mod.abs_pos):
                new_row = row.to_dict()

                mod_name = "{}{}-p".format(mod.letter, abs_pos + 1)

                new_row["ID"] = ",".join([gene, mod_name])
                new_rows.append(new_row)

    ds.psms.apply(_split_rows, axis=1)

    df = pd.DataFrame(new_rows, columns=list(ds.psms.columns) + ["ID"])

    return df


def _get_protein_ids(psms, species):
    if "Proteins" in psms.columns:
        return psms["Proteins"].apply(
            lambda row:
            brs.mapping.get_entrez_mapping(
                row.genes[0],
                species=species,
            ),
        )
    else:
        return psms["Gene"].apply(
            lambda row:
            brs.mapping.get_entrez_mapping(
                row,
                species=species,
            ),
        )


def get_pathways(species, p_sites=False, remap=False):
    """
    Download all default gene sets and phospho sets.

    Parameters
    ----------
    species : str
    p_sites : bool, optional
    remap : bool, optional

    Returns
    -------
    :class:`pandas.DataFrame`, optional
    """
    LOGGER.info(
        "building gene sets (psites={}, remap={})"
        .format(p_sites, remap)
    )

    if p_sites:
        pathways_df = psp.get_phosphosite(species, remap=remap)
        # pathways_df = pathways_df.append(
        #     get_phosphosite_regulation(species, remap=remap)
        # )
    else:
        pathways_df = wikipathways.get_wikipathways(species)

        if species in ["Homo sapiens", "human"] or remap:
            # pathways_df = pathways_df.append(
            #     pathwayscommon.get_pathway_common(species)
            # )
            pathways_df = pathways_df.append(
                msigdb.get_msigdb_pathways(species, remap=remap)
            )

        # if species in ["Mus musculus"]:
        #     pathways_df = pathways_df.append(gskb.get_gskb_pathways(species))

    LOGGER.info("Loaded {} gene sets".format(pathways_df.shape[0]))

    return pathways_df.reset_index()


def _filter_ambiguous_peptides(ds):
    LOGGER.info(
        "filtering ambiguous peptides ({} proteins)".format(len(set(ds.genes)))
    )

    ds = ds.filter(fn=lambda x: len(x["Proteins"].genes) == 1)
    ds = ds.filter(ambiguous=False)

    LOGGER.info("filtered down to {} proteins".format(len(set(ds.genes))))

    return ds


def _get_scores(psms, phenotype=None, metric="spearman"):
    LOGGER.info("building correlations using metric '{}'".format(metric))

    psms = psms[~psms["ID"].isnull()]

    agg = {}

    if "Fold Change" in psms.columns:
        agg["Fold Change"] = np.nanmedian
        agg["Fold Change"] = np.max

    if phenotype is not None:
        agg.update({
            # chan: np.nanmedian
            chan: np.max
            for chan in phenotype.index
        })

    psms = psms.groupby(
        by="ID",
        as_index=False,
    ).agg(agg)

    if phenotype is not None and metric in ["spearman", "pearson"]:
        phenotype = pd.to_numeric(phenotype)

        psms = psms[
            (~psms[phenotype.index].isnull()).sum(axis=1) >=
            enrichments.MIN_PERIODS
        ]

    psms = enrichments.correlate_phenotype(
        psms,
        phenotype=phenotype,
        metric=metric,
    )

    if "Correlation" in psms.columns:
        psms = psms[
            ~psms["Correlation"].isnull()
        ]

    return psms


def _get_set_name(cols):
    for name in [
        ["hit_list"],
        ["set"],
        ["up_set", "down_set"],
    ]:
        if any([i in cols for i in name]):
            return name


def filter_fn(vals, ds=None, species=None):
    if isinstance(vals, pd.Series):
        col_names = _get_set_name(vals.index)
    else:
        col_names = _get_set_name(vals.columns)

    def _p_site_isin(row):
        return any([
            (acc, mod.letter, abs_pos + 1) in v_set
            for acc in row["Proteins"].accessions
            for mod in row["Sequence"].modifications.mods
            for abs_pos in mod.abs_pos
        ])

    if not species and ds:
        species = list(ds.species)[0]

    def _gene_isin(row):
        return any([
            brs.mapping.get_entrez_mapping(gene, species=species) in v_set
            for gene in row["Proteins"].genes
        ])

    if isinstance(vals, pd.Series):
        p_sites = any(
            "," in i
            for col in col_names
            for i in vals[col]
        )
    else:
        p_sites = (
            vals.shape[0] > 0 and
            any(
                "," in list(vals.iloc[0][col])[0]
                for col in col_names
            )
        )

    if p_sites:
        if isinstance(vals, pd.Series):
            v_set = set(
                (
                    x.split(",")[0],
                    x.split(",")[1][0],
                    int(x.split(",")[1][1:].split("-")[0]),
                )
                for col in col_names
                for x in vals[col]
            )
        else:
            v_set = set(
                tup
                for col in col_names
                for val_set in vals[col].apply(
                    lambda s:
                    set(
                        (
                            x.split(",")[0],
                            x.split(",")[1][0],
                            int(x.split(",")[1][1:].split("-")[0]),
                        )
                        for x in s
                    ),
                )
                for tup in val_set
            )

        fn = _p_site_isin
    else:
        if isinstance(vals, pd.Series):
            v_set = set(
                i
                for col in col_names
                for i in vals[col]
            )
        else:
            v_set = set(
                acc
                for col in col_names
                for set in vals[col]
                for acc in set
            )

        fn = _gene_isin

    return fn


def gsea(
    psms=None,
    ds=None,
    gene_sets=None,
    metric="spearman",
    phenotype=None,
    species=None,
    min_hits=10,
    p_sites=False,
    remap=True,
    name=None,
    folder_name=None,
    **kwargs
):
    """
    Perform Gene Set Enrichment Analysis (GSEA) on a data set.

    Parameters not listed below will be passed on to the underlying enrichments
    module. See :func:`pyproteome.analysis.enrichments.plot_gsea` for a full
    list of arguments.

    Parameters
    ----------
    ds : :class:`DataSet<pyproteome.data_sets.DataSet>`
        The data set to perform enrichment analysis on.
    phenotype : :class:`pandas.Series`, optional
        A series object with index values equal to the quantification columns
        in the data set. This object is used when calculating correlation
        statistics for each peptide.
    name : str, optional
        The name of this analysis. Defaults to `ds.name`.
    metric : str, optional
        Correlation metric to use.

        Can be one of ["zscore", "fold", "spearman", "pearson", "kendall"].
    p_sites : bool, optional
        Perform Phospho Set Enrichment Analysis (PSEA) on data set.
    remap : bool, optional
        Remap database of phosphosites using information from all species.
    species : str, optional
        The species used to generate gene sets.

        Value should be in binomial nomenclature (i.e. "Homo sapiens",
        "Mus musculus").

        If different from that of the input data set, IDs will be mapped to
        the target species using Phosphosite Plus's database.
    min_hits : int, optional
    gene_sets : :class:`pandas.DataFrame`, optional
        A dataframe with two columns: "name" and "set".

        Each element of set should be a Python set() object containing all the
        gene IDs for each gene set.

        Gene IDs should be strings of Entrez Gene IDs for protein sets and
        strings of "<Entrez>,<letter><pos>-p" (i.e. "8778,Y544-p") for
        phospho sets.
    folder_name : str, optional
        Save figures and tables to this folder. Defaults to `<ds.name>/GSEA`

    See Also
    --------
    :func:`pyproteome.analysis.enrichments.enrichment_scores`
    :func:`pyproteome.analysis.enrichments.plot_gsea`

    Returns
    -------
    vals : :class:`pandas.DataFrame`
    gene_changes : :class:`pandas.DataFrame`
    """
    assert psms is not None or ds is not None

    folder_name = pyp.utils.make_folder(
        data=ds,
        folder_name=folder_name,
        sub="PSEA" if p_sites else "GSEA",
    )

    if ds is not None:
        ds = _filter_ambiguous_peptides(ds)

        if species is None:
            species = list(ds.species)[0]

        if name is None:
            name = "{}-{}".format(
                ds.name,
                "PSEA" if p_sites else "GSEA",
            )

        if p_sites:
            psms = _get_psite_ids(ds, species)
        else:
            psms = ds.psms.copy()
            psms["ID"] = _get_protein_ids(psms, species)

        if species not in ds.species:
            psms = _remap_data(
                psms,
                from_species=list(ds.species)[0],
                to_species=species,
            )
    else:
        psms["ID"] = _get_protein_ids(psms, species)

    if gene_sets is None:
        gene_sets = get_pathways(species, p_sites=p_sites, remap=remap)

    psms = _get_scores(
        psms,
        phenotype=phenotype,
        metric=metric,
    )

    es_args = {
        "phenotype": phenotype,
        "metric": metric,
    }
    es_args.update({
        i: kwargs.pop(i)
        for i in ["p", "pval", "p_iter", "n_cpus"]
        if i in kwargs
    })

    gene_changes = enrichments.get_gene_changes(psms)

    gene_sets = enrichments.filter_gene_sets(
        gene_sets, psms,
        min_hits=min_hits,
    )

    vals = enrichments.enrichment_scores(
        psms,
        gene_sets,
        **es_args
    )

    if name is None:
        name = "PSEA" if p_sites else "GSEA"

    vals.to_csv(
        os.path.join(
            folder_name,
            name + ".csv",
        ),
    )

    enrichments.plot_gsea(
        vals, gene_changes,
        folder_name=folder_name,
        name=name,
        **kwargs
    )

    return vals, gene_changes


def psea(*args, **kwargs):
    """
    Perform Gene Set Enrichment Analysis (GSEA) on a data set.

    See :func:`pyproteome.analysis.pathways.gsea` for documentation and a full
    list of arguments.

    Returns
    -------
    :class:`pandas.DataFrame`, optional
    """
    kwargs["p_sites"] = True
    return gsea(*args, **kwargs)