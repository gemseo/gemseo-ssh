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
from __future__ import annotations

from pathlib import Path

from gemseo.core.discipline.discipline import Discipline


class DiscWithFiles(Discipline):
    """A dummy discipline that handles files in inputs and outputs."""

    default_grammar_type = Discipline.GrammarType.SIMPLE

    def __init__(self):  # noqa: D107
        super().__init__()
        self.input_grammar.update_from_types({"in_file": str, "discipline": str})
        self.output_grammar.update_from_types({"out_file": str, "out_val": int})

    def _run(self, input_data):
        in_file_path = Path(self.io.data["in_file"])
        out_val = int(in_file_path.read_text()) + 1
        out_path = in_file_path.parent / "out_file.txt"
        out_path.write_text(str(out_val), encoding="utf8")

        self.io.data["out_val"] = out_val
        self.io.data["out_file"] = str(out_path)
