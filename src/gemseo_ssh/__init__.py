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
    local_workdir: str | Path,
    hostname: str,
    port: int,
    username: str,
    password: str,
    ssh_public_key: str | Path,
    authentification_method: SSHDisciplineWrapper.AuthentificationMethod,
    remote_workdir: str | Path,
    pre_commands: Sequence[str],
    transfer_inputs=None,
    transfer_outputs=None,
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
        local_workdir=local_workdir,
        hostname=hostname,
        port=port,
        username=username,
        password=password,
        ssh_public_key=ssh_public_key,
        authentification_method=authentification_method,
        remote_workdir=remote_workdir,
        pre_commands=pre_commands,
        transfer_inputs=transfer_inputs,
        transfer_outputs=transfer_outputs,
    )
