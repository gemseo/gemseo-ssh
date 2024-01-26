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
"""Main entry point for executing discipline via ssh."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from gemseo.core.discipline import MDODiscipline

    from gemseo_ssh.wrappers.ssh.ssh_wrapped_disc import SSHDisciplineWrapper


def wrap_discipline_with_ssh(
    discipline: MDODiscipline,
    local_workdir_path: str | Path,
    hostname: str,
    remote_workdir_path: str | Path = "",
    pre_commands: Iterable[str] = (),
    transfer_input_names: Iterable[str] = (),
    transfer_output_names: Iterable[str] = (),
    **ssh_client_parameters: Any,
) -> SSHDisciplineWrapper:
    """Wrap the discipline within the SSH transfer discipline.

    The discipline is serialized to the disk, its input too, then a job file is
    created from a template to execute it with the provided options.
    The submission command is launched, it will setup the environment, deserialize
    the discipline and its inputs, execute it and serialize the outputs.
    Finally, the deserialized outputs are returned by the wrapper.

    Args:
        discipline: The discipline to wrap and execute on the remote host.
        local_workdir_path: The path to the work directory on the local host.
        hostname: The name of the remote host to delegate the execution.
        remote_workdir_path: The path to the work directory on the remote host.
        pre_commands: The commands run on the remote host before deserialization and
            execution of the discipline on the remote host. This can be used to activate
            the Python environment for instance.
        transfer_input_names: The names of the discipline inputs that correspond
            to files that must be transferred before execution.
        transfer_output_names: The names of the discipline outputs that correspond
            to files that must be transferred after execution.
        **ssh_client_parameters: The optional parameters to pass to paramiko.SSHClient.

    Raises:
        KeyError: if the transfer_inputs or transfer_outputs arguments are inconsistent
            with the discipline grammars.
    """
    from gemseo_ssh.wrappers.ssh.ssh_wrapped_disc import SSHDisciplineWrapper

    return SSHDisciplineWrapper(
        discipline=discipline,
        local_workdir_path=local_workdir_path,
        hostname=hostname,
        remote_workdir_path=remote_workdir_path,
        pre_commands=pre_commands,
        transfer_input_names=transfer_input_names,
        transfer_output_names=transfer_output_names,
        **ssh_client_parameters,
    )
