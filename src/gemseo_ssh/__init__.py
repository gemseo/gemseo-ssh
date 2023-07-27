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
"""Wrappers."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence
from typing import TYPE_CHECKING

from gemseo.core.discipline import MDODiscipline

if TYPE_CHECKING:
    from gemseo_ssh.wrappers.ssh.ssh_wrapped_disc import SSHDisciplineWrapper


def wrap_discipline_with_ssh(
        discipline: MDODiscipline,
        local_workdir_path: str | Path,
        hostname: str,
        port: int = 22,
        username: str = "",
        password: str = "",
        ssh_public_key: str | Path = None,
        authentication_method: SSHDisciplineWrapper.AuthenticationMethod = SSHDisciplineWrapper.AuthenticationMethod.PASSWORD,
        remote_workdir_path: str | Path = None,
        pre_commands: Sequence[str] = (),
        transfer_inputs: Sequence[str] = (),
        transfer_outputs: Sequence[str] = (),
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
        port: The port to use for SSH.
        username: The user name on the remote host.
        password: The password associated to the username on the remote host.
            Used when the authentication_method is
            SSHDisciplineWrapper.AuthenticationMethod.PASSWORD
        ssh_public_key: The public key used for authentication on the remote host.
            Used when the authentication_method is
            SSHDisciplineWrapper.AuthenticationMethod.PUBLIC_KEY
        authentication_method: The method used for authentication on the remote host.
            Either public keys must be setup, or the plain password.
        remote_workdir_path: The path to the work directory on the remote host.
        pre_commands: The commands run on the remote host before deserialization and
            execution of the discipline on the remote host. This can be used to load
            the Python environment for instance.
        transfer_inputs: The sequence of files input data names that
            must be transferred before execution.
        transfer_outputs: The sequence of files output data names that
            must be transferred after execution.

    Raises:
        KeyError: if the transfer_inputs or transfer_outputs arguments are inconsistent
            with the discipline grammars.
    """
    from gemseo_ssh.wrappers.ssh.ssh_wrapped_disc import SSHDisciplineWrapper

    return SSHDisciplineWrapper(
        discipline=discipline,
        local_workdir_path=local_workdir_path,
        hostname=hostname,
        port=port,
        username=username,
        password=password,
        ssh_public_key=ssh_public_key,
        authentication_method=authentication_method,
        remote_workdir_path=remote_workdir_path,
        pre_commands=pre_commands,
        transfer_inputs=transfer_inputs,
        transfer_outputs=transfer_outputs,
    )
