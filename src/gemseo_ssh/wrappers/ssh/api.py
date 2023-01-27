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
# Copyright 2023 IRT Saint Exupéry, https://www.irt-saintexupery.com
"""API for SSH Transfer discipline."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Sequence

from gemseo.core.discipline import MDODiscipline


def wrap_discipline(
    discipline: MDODiscipline,
    local_workdir_path: str | Path,
    hostname: str,
    port: int,
    username: str,
    password: str,
    ssh_public_key: str | Path,
    authentification_method: Enum,
    distant_workdir_path: str | Path,
    pre_commands: Sequence[str],
):
    """Wrap the discipline within the SSH transfer discipline.

    The discipline is serialized to the disk, its input too, then a job file is
    created from a template to execute it with the provided options.
    The submission command is launched, it will setup the environment, deserialize
    the discipline and its inputs, execute it and serialize the outputs.
    Finally, the deserialized outputs are returned by the wrapper.

    Args:
        discipline: The discipline to wrapp in the job scheduler.
        local_workdir_path: The path to the workdir

    Raises:
        OSError if the job template does not exist.
    """
    from gemseo_ssh.wrappers.ssh.ssh_wrapped_disc import SSHDisciplineWrapper

    return SSHDisciplineWrapper(
        discipline=discipline,
        workdir_path=local_workdir_path,
        hostname=hostname,
        port=port,
        username=username,
        password=password,
        ssh_public_key=ssh_public_key,
        authentification_method=authentification_method,
        distant_workdir=distant_workdir_path,
        pre_commands=pre_commands,
    )
