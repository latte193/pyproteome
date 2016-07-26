"""
Provides functionality for exporting processed data to .camv files (JSON
format).
"""

from collections import OrderedDict
import json
import re

from .utils import DefaultOrderedDict

from . import ms_labels
from pyproteome.loading import RE_PROTEIN


def _peaks_to_dict(peaks):
    return [
        OrderedDict([
            ("mz", mz),
            ("into", i),
        ])
        for mz, i in peaks
    ]


def _extract_pep_seq(sequence):
    return "".join(
        letter
        for letter, _ in sequence
        if letter not in ["N-term", "C-term"]
    )


def _extract_mods(sequence):
    return tuple(
        tuple(mods)
        for _, mods in sequence
    )


def _count_mods(pep_seq, pep_mods):
    return sum(
        bool(mods)
        for letter, mods in zip(pep_seq, pep_mods)
        if letter not in ["N-term", "C-term"]
    )


def _get_mods_description(pep_seq, mods):
    return "+{}".format(_count_mods(pep_seq, mods))


def _mod_positions(mods):
    return [
        index
        for index, mod in enumerate(mods)
        if mod
    ]


def _pep_mod_name(pep_seq, mods):
    return "".join(
        letter.lower() if mods else letter.upper()
        for letter, mods in zip(pep_seq, mods[1:-1])
    )


def _get_labels_mz(query):
    return [
        mz
        for var_mod in query.pep_var_mods
        for mz in ms_labels.LABEL_MASSES.get(var_mod, [])
    ]


def export_to_camv(out_path, peak_hits, precursor_windows, label_windows):
    """
    Export data to .camv file.

    Parameters
    ----------
    out_path : str

    Returns
    -------
    data : dict
        Dictionary of data written to file.
    """
    ###
    # Mappings between proteins, peptides, modifications, queries, and peaks
    ###
    # Mapping for protein -> peptides
    prot_dict = DefaultOrderedDict(set)

    for query, _ in peak_hits.keys():
        prot_dict[RE_PROTEIN.match(query.protein).group(1)].add(query.pep_seq)

    pep_dict = DefaultOrderedDict(set)

    for query, _ in peak_hits.keys():
        pep_dict[query.pep_seq].add(tuple(query.pep_var_mods))

    mod_states_dict = DefaultOrderedDict(set)

    for query, seq in peak_hits.keys():
        mod_states_dict[query.pep_seq, tuple(query.pep_var_mods)].add(
            _extract_mods(seq)
        )

    # Mapping for modifications -> queries
    mods_dict = DefaultOrderedDict(list)

    for query, seq in peak_hits.keys():
        mods_dict[query.pep_seq, _extract_mods(seq)].append(query)

    # Mapping for queries -> sequence + modifications
    query_dict = DefaultOrderedDict(list)

    for (query, seq), hits in peak_hits.items():
        query_dict[query].append((query.pep_seq, _extract_mods(seq)))

    # Mapping for queries -> peak hits
    scan_data = {
        query: hits
        for (query, _), hits in peak_hits.items()
    }

    ###
    # Pre-calculate IDs for later reference
    ###
    # Protein IDs
    prot_index = {
        prot_name: index
        for index, prot_name in enumerate(prot_dict.keys())
    }

    # Peptide Data IDs
    pep_data_index = {}
    index = 0
    for peptides in prot_dict.values():
        for pep_seq in peptides:
            pep_data_index[pep_seq] = index
            index += 1

    # Peptide IDs
    pep_index = {}
    index = 0
    for pep_seq, mod_states in pep_dict.items():
        for mod_state in mod_states:
            pep_index[pep_seq, mod_state] = index
            index += 1

    # Mod State IDs
    mod_state_index = {
        (pep_seq, mod_state): index
        for pep_seq, mod_states in pep_dict.items()
        for index, mod_state in enumerate(mod_states)
    }

    # Modification IDs
    mod_index = {
        (pep_seq, mod): index
        for (pep_seq, _), mods in mod_states_dict.items()
        for index, mod in enumerate(mods)
    }

    # Scan IDs
    scan_index = {
        query: index
        for pep_seq, mods in pep_dict.items()
        for mod in mods
        for index, (query, _) in enumerate(mods_dict[mod])
    }

    # Peak Match IDs
    match_index = {}

    for (_, seq), hits in peak_hits.items():
        index = 0

        for peak_hit in hits:
            if not peak_hit.match_list:
                continue

            for name in peak_hit.match_list.keys():
                match_index[_extract_pep_seq(seq), name] = index
                index += 1

    ###
    # Individual data parsing functions
    ###
    def _gen_match_data(seq, peaks):
        """
        Generate a list of all potential peak matches
        """
        for peak_hit in peaks:
            if not peak_hit.match_list:
                continue

            for name, (mz, _) in peak_hit.match_list.items():
                name_split = re.split("[_\^]", name)
                name_split = [i.strip("{}") for i in name_split]

                ion_type, ion_pos = None, None

                if name_split[0] in "abc":
                    ion_type, ion_pos = "b", int(name_split[1])
                elif name_split[0] in "xyz":
                    ion_type, ion_pos = "y", int(name_split[1])

                yield OrderedDict([
                    ("id", match_index[seq, name]),
                    ("mz", mz),
                    ("name", name),
                    ("ionType", ion_type),
                    ("ionPosition", ion_pos),
                ])

    def _get_match_data(seq, peaks):
        return list(_gen_match_data(seq, peaks))

    def _get_mod_data(pep_seq, mods):
        return [
            OrderedDict([
                ("id", mod_index[pep_seq, mod]),
                ("position", _mod_positions(mod)),
                ("name", _pep_mod_name(pep_seq, mod)),
                (
                    "matchData",
                    _get_match_data(
                        pep_seq,
                        # XXX: All queries?
                        scan_data[mods_dict[pep_seq, mod][0]],
                    ),
                ),
            ])
            for mod in mods
        ]

    def _get_mod_states(pep_seq, mod_states):
        return [
            OrderedDict([
                ("id", mod_state_index[pep_seq, mod_state]),
                ("modDesc", _get_mods_description(pep_seq, mod_state)),
                (
                    "mods",
                    _get_mod_data(
                        pep_seq,
                        mod_states_dict[pep_seq, mod_state],
                    ),
                ),
            ])
            for mod_state in mod_states
        ]

    def _get_peptide_data():
        """
        Return all information mapping (modified) peptides to their sequence,
        descriptions, ion fragmentation patterns, etc.
        """
        return [
            OrderedDict([
                ("id", pep_data_index[pep_seq]),
                ("peptideSequence", pep_seq),
                ("modificationStates", _get_mod_states(pep_seq, mod_states)),
            ])
            for pep_seq, mod_states in pep_dict.items()
        ]

    #
    def _get_default_choice_data(pep_seq, mods):
        return [
            OrderedDict([
                ("modsId", mod_index),
                ("state", None),  # null
            ])
            for mod_index, _ in enumerate(mods_dict[pep_seq, mods])
        ]

    def _get_scan_assignments(query, seq):
        return [
            OrderedDict([
                ("mz", peak_hit.mz),
                ("into", peak_hit.intensity),
                (
                    "matchInfo",
                    [
                        OrderedDict([
                            ("modsId", mod_index[seq, mods]),
                            (
                                "matchId",
                                match_index.get(
                                    (seq, peak_hit.name),
                                    None,
                                ),
                            )
                        ])
                        for _, mods in query_dict[query]
                    ],
                ),
            ])
            for peak_hit in peak_hits[query, seq]
        ]

    def _get_scans(pep_seq, mods):
        """
        Return information on individual scans, including peaks, precursor
        ions, and peptide modification assignments.
        """
        return [
            OrderedDict([
                ("scanNumber", query.scan),
                ("scanId", scan_index[query]),
                ("chargeState", query.pep_exp_z),
                (
                    "precursorScanData",
                    _peaks_to_dict(precursor_windows[query]),
                ),
                ("precursorMz", query.pep_exp_mz),
                ("quantScanData", _peaks_to_dict(label_windows[query])),
                ("quantMz", _get_labels_mz(query)),
                ("choiceData", _get_default_choice_data(pep_seq, mods)),
                ("scanData", _get_scan_assignments(query)),
            ])
            for query in mods_dict[pep_seq, mods]
        ]

    def _get_peptide_scan_data(peptides):
        """
        Map peptides to their data IDs, scans, and candidate modification
        states.
        """
        return [
            OrderedDict([
                ("peptideId", pep_index[pep_seq, mod_state]),
                ("peptideDataId", pep_data_index[pep_seq]),
                ("modificationStateId", mod_state_index[pep_seq, mod_state]),
                ("scans", _get_scans(pep_seq, mod_state)),
            ])
            for pep_seq in peptides
            for mod_state in pep_dict[pep_seq]
        ]

    #
    def _get_scan_data():
        """
        Return all information mapping proteins / peptides to their scans and
        a list of candidate modification patterns.
        """
        return [
            OrderedDict([
                ("proteinName", prot_name),
                ("proteinId", prot_index[prot_name]),
                ("peptides", _get_peptide_scan_data(peptides)),
            ])
            for prot_name, peptides in prot_dict.items()
        ]

    data = OrderedDict([
        ("peptideData", _get_peptide_data()),
        ("scanData", _get_scan_data()),
    ])

    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    return data