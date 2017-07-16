# -*- coding: utf-8 -*-
from __future__ import division

# Built-ins
import logging
import math
import requests
import time

try:
    from IPython.display import Image
except ImportError:
    Image = None

from . import motif

LOGGER = logging.getLogger("pyproteome.plogo")
PLOGO_BASE = "https://plogo.uconn.edu/main"


def _format_title(data, f):
    title = []

    if 'fold_cutoff' in f:
        title.append(
            "abs(FC) > {:.2f}".format(f['fold_cutoff'])
        )

    if 'asym_fold_cutoff' in f:
        title.append(
            "FC {} {:.2f}".format(
                ">" if f["asym_fold_cutoff"] > 1 else "<",
                f['asym_fold_cutoff'],
            )
        )

    if 'p_cutoff' in f:
        title.append(
            "p < {:.2f}".format(f['p_cutoff'])
        )

    return "{} - {}".format(data.name, ", ".join(title))


def make_logo(data, f, m=None, letter_mod_types=None, **kwargs):
    if letter_mod_types is None:
        letter_mod_types = [(None, "Phospho")]

    fore = [
        n
        for n in motif.generate_n_mers(
            data.filter(**f)["Sequence"],
            letter_mod_types=letter_mod_types,
        )
        if not m or m.match(n)
    ]

    back = [
        n
        for n in motif.generate_n_mers(
            data["Sequence"],
            letter_mod_types=letter_mod_types,
        )
    ]
    return plogo(
        fore, back,
        title=_format_title(data, f),
        **kwargs
    )


def plogo_wait_job(s, job, delay=1):
    while True:
        response = s.get(
            '{}/getPlogo/{}'.format(PLOGO_BASE, job),
        )
        response.raise_for_status()
        json = response.json()

        if json['complete']:
            break

        time.sleep(delay)


def _check_plogo_response(response, message=""):
    response.raise_for_status()
    json = response.json()
    assert json["message"] == message
    assert json["success"]
    return json


def plogo(
    foreground, background,
    fix_letter_pos=None,
    title="",
    width=800,
    height=600,
    ymax=None,
):
    u"""
    Wraps calls to Plogo, returning an image showing the enrichment of a
    sequence in a foreground set compared to a background set.

    Notes
    -----
    .. [1] O’Shea, Joseph P et al. “pLogo: A Probabilistic Approach to
       Visualizing Sequence Motifs.” Nature Methods 10.12 (2013): 1211–1212.
       Web.
    """
    if fix_letter_pos is None:
        fix_letter_pos = []

    assert len(foreground) > 0
    assert len(background) > 0

    letter_width = len(background[0])

    s = requests.Session()

    response = s.post(
        '{}/uploadforeground/'.format(PLOGO_BASE),
        data={
            'fg': "\n".join(foreground),
            'fix': 1,
            'dataType': 'text',
            'remove_duplicates': True,
        },
    )
    json = _check_plogo_response(
        response, message="Foreground uploaded. See stats.",
    )
    fore_dir = json['dir']

    response = s.post(
        '{}/uploadbackground/'.format(PLOGO_BASE),
        data={
            'bg_text': "\n".join(background),
            'dataType': 'text',
            'datasetType': None,
            'name': 'unknown',
            'remove_duplicates': True,
        },
    )
    json = _check_plogo_response(response)
    back_dir = json['dir']
    assert fore_dir == back_dir

    response = s.post(
        '{}/initplogo/'.format(PLOGO_BASE),
        data={
            'width': letter_width,
            'fixedLetter': 'S',
            'fixedPosition': 7,
            'fix': 0,
            'jobName': 'pyproteome.motif.plogo',
            'subtract_fg': False,
            'remove_duplicates': True,
            'from_ksdb': False,
        },
    )

    json = _check_plogo_response(response)
    job = json['state']['jobId']
    plogo_wait_job(s, job)

    for letter, pos in fix_letter_pos:
        response = s.post(
            '{}/initplogo/'.format(PLOGO_BASE),
            data={
                'width': letter_width,
                'fixedLetter': letter,
                'fixedPosition': math.floor(letter_width / 2) + pos,
                'fix': 1,
                'jobName': 'pyproteome.motif.plogo - fix',
                'subtract_fg': False,
                'remove_duplicates': True,
                'from_ksdb': False,
                'referenceId': job,
            },
        )

        json = _check_plogo_response(response)
        job = json['state']['jobId']
        plogo_wait_job(s, job)

    response = s.post(
        '{}/redrawplogo/'.format(PLOGO_BASE),
        data={
            'options[title]': title,
            'options[width]': width,
            'options[height]': height,
            'options[plogoMode]': 'absolute',
            'options[maxAbsoluteValue]': ymax,
            'jobId': job,
        },
    )
    json = _check_plogo_response(response)
    job = json['state']['jobId']
    plogo_wait_job(s, job)

    png = json['state']['job']['image_url']

    if Image:
        return Image(url=png)
    else:
        return png