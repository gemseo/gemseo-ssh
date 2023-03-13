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
from __future__ import annotations

from pathlib import Path

from gemseo_ssh.problems.dummy_disc_with_files import DiscWithFiles


def test_exec(tmpdir):
    """Test execution."""
    disc = DiscWithFiles(tmpdir)

    in_path = tmpdir / "in_f.txt"
    with open(in_path, "w") as infile:
        infile.write("0")
    out = disc.execute({"in_file": str(in_path)})
    assert out["out_val"] == 1

    assert Path(out["out_file"]).exists()
