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

from gemseo.discipline import Discipline


class DiscWithFiles(Discipline):
    """A dummy discipline that handles files in inputs and outputs."""

    default_grammar_type = Discipline.GrammarType.SIMPLE

    def __init__(self):  # noqa: D107
        super().__init__()
        self.input_grammar.update_from_types({"in_file": str, "discipline": str})
        self.output_grammar.update_from_types({"out_file": str, "out_val": int})

    def _run(self, input_data):
        # TODO(bump-gemseo): IO.data is deprecated and returns a copy of the input and output data, so setting, updating or removing an item through it has no effect, and an output that _run produces through it is missing, even when produced by changing an input in place; return the outputs from _run or write them to output_data (or update_output_data(data)), write the inputs to input_data, and read input_data, output_data or get_merged_data()  # noqa: E501
        in_file_path = Path(self.io.data["in_file"])
        out_val = int(in_file_path.read_text()) + 1
        out_path = in_file_path.parent / "out_file.txt"
        out_path.write_text(str(out_val), encoding="utf8")

        # TODO(bump-gemseo): self.io.data[...] = ... became self.io.output_data[...] = ..., the key being assumed to be an output; if it names an input, write it to self.io.input_data instead  # noqa: E501
        self.io.output_data["out_val"] = out_val
        # TODO(bump-gemseo): self.io.data[...] = ... became self.io.output_data[...] = ..., the key being assumed to be an output; if it names an input, write it to self.io.input_data instead  # noqa: E501
        self.io.output_data["out_file"] = str(out_path)
