
import os
from setuptools import setup, find_packages

__dir__ = os.path.dirname(__file__)

with open(
    os.path.join(__dir__, "pyproteome", "version.py")
) as f:
    __version__ = "0.0.0"

    for line in f:
        if "#" in line:
            line = line[:line.index("#")]

        if not line.startswith("version ="):
            continue

        __version__ = line.split("=")[1].strip().strip("\"")

REQUIREMENTS = [
    "adjustText>=0.7.3",
    "fastcluster>=1.1.25",
    "genemap>=0.2.0",
    "ipython>=5.4.1",
    "matplotlib>=2.2.0",
    "numpy>=1.15.0",
    "numpydoc>=0.8",
    "pandas>=0.23.0",
    "perseuspy>=0.3.8",
    "photon_ptm>=0.3.0",
    "scikit-learn>=0.19.1",
    "scipy>=1.1.0",
    "seaborn>=0.9.0",
    "uniprot==1.3",
    "xlrd>=1.1.0",
    "xlwt>=1.3.0",
    "xlsxwriter>=1.0.5",
]

if __name__ == "__main__":
    setup(
        name="pyproteome",
        version=__version__,
        description="Package for managing proteomics data",
        url="https://github.com/white-lab/pyproteome",
        author="Nader Morshed",
        author_email="morshed@mit.edu",
        license="BSD",
        packages=find_packages(exclude=["*.tests", "tests"]),
        install_requires=REQUIREMENTS,
        dependency_links=[
            "git+https://github.com/naderm/genemap.git"
            "@master#egg=genemap-0.2.0",
            "git+https://github.com/naderm/perseuspy.git"
            "@master#egg=perseuspy-0.3.8",
        ],
        classifiers=[
            "License :: OSI Approved :: BSD License",
            "Natural Language :: English",
            "Operating System :: OS Independent",
            "Programming Language :: Python :: 2",
            "Programming Language :: Python :: 2.7",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.4",
            "Programming Language :: Python :: 3.5",
            "Programming Language :: Python :: 3.6",
            "Programming Language :: Python :: 3.7",
            "Topic :: Scientific/Engineering",
        ],
        test_suite="tests",
    )
