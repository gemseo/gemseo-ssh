# Copyright 2023 IRT Saint Exupéry, https://www.irt-saintexupery.com
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
# Contributors:
#    INITIAL AUTHORS - API and implementation and/or documentation
#        :author: Francois Gallard
#    OTHER AUTHORS   - MACROSCOPIC CHANGES
"""Dummy files based discipline."""
from __future__ import annotations

from pathlib import Path

from gemseo.core.discipline import MDODiscipline


class DiscWithFiles(MDODiscipline):
    """A dummy discipline that handles files in inputs and outputs."""

    def __init__(self, workdir):
        """Constructor.

        Args:
            workdir: The working directory where files are created.
        """
        super().__init__(grammar_type=DiscWithFiles.SIMPLE_GRAMMAR_TYPE)
        self.input_grammar.update({"in_file": str})
        self.output_grammar.update({"out_file": str, "out_val": int})
        self.workdir = workdir

    def _run(self):
        with open(self.local_data["in_file"]) as inf:
            values = int(inf.read())

        out_val = values + 1
        out_path = Path(self.workdir) / "out_file.txt"
        with open(out_path, "w") as outf:
            outf.write(str(out_val))

        self.local_data["out_val"] = out_val
        self.local_data["out_file"] = str(out_path)
