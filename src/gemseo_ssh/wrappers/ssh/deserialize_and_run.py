# Copyright 2021 IRT Saint Exupéry, https://www.irt-saintexupery.com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""Serialize/Deserialize and run a discipline."""
from __future__ import annotations

import os
import pickle
import sys
import traceback
from pathlib import Path


def _parse_inputs(args):
    if len(args) < 5:
        msg = (
            "Usage : python deserialize_and_run.py local_workdir_path "
            "discipline_path inputs_path output_path"
        )
        raise RuntimeError(msg)

    workir_path = Path(args[1])
    if not workir_path.exists():
        raise RuntimeError(f"Work directory {workir_path} does not exist.")

    serialized_disc_path = Path(args[2])
    if not serialized_disc_path.exists():
        raise RuntimeError(
            "Path to serialized discipline {} does not exist.".format(
                serialized_disc_path
            )
        )

    input_data_path = Path(args[3])
    if not input_data_path.exists():
        raise RuntimeError(
            f"Path to serialized input data {input_data_path} does not exist."
        )

    outputs_path = Path(args[4])

    return workir_path, serialized_disc_path, input_data_path, outputs_path


def _load_disc_and_inputs(serialized_disc_path, input_data_path):
    with serialized_disc_path.open("rb") as discipline_file:
        discipline = pickle.load(discipline_file)

    with input_data_path.open("rb") as input_data_file:
        input_data = pickle.load(input_data_file)

    return discipline, input_data


def _run_discipline_save_outputs(discipline, input_data, outputs_path, workir_path):
    cwd = os.getcwd()
    os.chdir(workir_path)

    try:
        outputs = discipline.execute(input_data)
    except Exception as error:
        trace = traceback.format_exc()
        outputs = (error, trace)

    with outputs_path.open("wb") as outfobj:
        pickler = pickle.Pickler(outfobj, protocol=2)
        pickler.dump(outputs)

    os.chdir(cwd)


def _main(args):
    workir_path, serialized_disc_path, input_data_path, outputs_path = _parse_inputs(
        args
    )
    discipline, input_data = _load_disc_and_inputs(
        serialized_disc_path, input_data_path
    )
    _run_discipline_save_outputs(discipline, input_data, outputs_path, workir_path)
    return discipline, outputs_path


def main():
    """Entry point."""
    _main(sys.argv)
    sys.exit(0)
