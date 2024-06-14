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

import os
import shutil
import subprocess
import venv
from pathlib import Path
from typing import NamedTuple
from unittest.mock import MagicMock

import pytest
from filelock import FileLock
from gemseo import create_discipline
from gemseo.problems.topology_optimization.volume_fraction_disc import VolumeFraction
from gemseo.utils.comparisons import compare_dict_of_arrays
from gemseo.utils.platform import PLATFORM_IS_WINDOWS
from paramiko import SSHClient as ParamikoSSHCLIENT

from gemseo_ssh import wrap_discipline_with_ssh
from gemseo_ssh.wrappers.ssh.paramiko import SSHClient as GemseoSSHClient

CURRENT_DIR_PATH = Path(__file__).parent

# The hostname does not matter since the ssh layer will be mocked.
HOSTNAME = "dummy"

if PLATFORM_IS_WINDOWS:
    VENV_REL_PATH_TO_PYTHON = "Scripts/python.exe"
    ACTIVATE_CMD = r"{venv_path}\Scripts\activate"
    SET_PYTHONPATH_CMD = "for /f \"delims=\" %a in ('cd') do @set PYTHONPATH=%a"
else:
    VENV_REL_PATH_TO_PYTHON = "bin/python"
    ACTIVATE_CMD = ". {venv_path}/bin/activate"
    SET_PYTHONPATH_CMD = "export PYTHONPATH={workdir_path}:$PYTHONPATH"


class SFTP:
    """Mock of the sftp client."""

    mkdir = os.mkdir
    chdir = os.chdir
    get = staticmethod(shutil.copyfile)
    put = staticmethod(shutil.copyfile)


def exec_command(self, cmd: str) -> tuple:
    """Mock the related command of the ssh client."""
    os.system(cmd)
    stdout = MagicMock()
    stdout.channel.recv_exit_status = MagicMock(return_value=0)
    return None, stdout, MagicMock()


# Mock the ssh client.
ParamikoSSHCLIENT.set_missing_host_key_policy = MagicMock()
ParamikoSSHCLIENT.load_system_host_keys = MagicMock()
ParamikoSSHCLIENT.connect = MagicMock()
ParamikoSSHCLIENT.get_transport = MagicMock()
ParamikoSSHCLIENT.exec_command = exec_command
GemseoSSHClient.open_sftp = MagicMock(side_effect=SFTP)


class RemoteSetup(NamedTuple):
    """Settings for the remote."""

    workdir_path: Path
    activation_cmd: str
    set_python_path_cmd: str


def test_helper_discipline(tmp_path):
    """Test execution."""
    from .discipline import DiscWithFiles

    disc = DiscWithFiles()

    in_path = tmp_path / "in_f.txt"
    in_path.write_text("0")

    out = disc.execute({
        "in_file": str(in_path),
        "discipline": "",
    })

    assert out["out_val"] == 1

    assert Path(out["out_file"]).exists()


def create_venv(path: Path):
    """Create a virtualenv with the same version of GEMSEO.

    Args:
        path: The path to the virtualenv root directory.
    """
    venv.create(path, with_pip=True)

    gemseo_version = "gemseo@git+https://gitlab.com/gemseo/dev/gemseo.git@develop"

    subprocess.run(
        f"{path / VENV_REL_PATH_TO_PYTHON} -m pip " f"install {gemseo_version}".split(),
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def remote_setup(tmp_path_factory, worker_id):
    """Create the virtual env for the remote connection on the local host."""
    workdir_path = tmp_path_factory.mktemp("ssh-remote-workdir")
    venv_path = workdir_path / "venv"

    # Safely creates the venv when executing the tests in parallel.
    if worker_id == "master":
        create_venv(venv_path)
    else:
        with FileLock(str(workdir_path / "fixture.lock")):
            create_venv(venv_path)

    return RemoteSetup(
        workdir_path,
        ACTIVATE_CMD.format(venv_path=venv_path),
        SET_PYTHONPATH_CMD.format(workdir_path=workdir_path),
    )


def test_linux(tmp_path, remote_setup):
    """Test the remote execution on a Linux env."""
    local_disc = create_discipline("SobieskiMission")
    pre_commands = [remote_setup.activation_cmd]

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        tmp_path,
        HOSTNAME,
        remote_workdir_path=remote_setup.workdir_path.as_posix(),
        pre_commands=pre_commands,
    )

    data = remote_disc.execute()

    ref_data = local_disc.execute()
    assert compare_dict_of_arrays(data, ref_data)


def test_linux_transfer(tmp_path, remote_setup, monkeypatch):
    """Test the remote execution on a Linux env with files transfers."""
    # For the picling to work,
    # the namespace of the discipline shall be accessible on the
    # remote host, this can be done by importing it absolutely the both
    # on local and remote hosts.
    monkeypatch.syspath_prepend(CURRENT_DIR_PATH)
    from discipline import DiscWithFiles

    local_disc = DiscWithFiles()

    pre_commands = [
        remote_setup.activation_cmd,
        # This allows unpickling the discipline on the remote host.
        remote_setup.set_python_path_cmd,
    ]

    in_path = tmp_path / "in_f.txt"
    in_path.write_text("0")

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        tmp_path,
        HOSTNAME,
        remote_workdir_path=remote_setup.workdir_path.as_posix(),
        pre_commands=pre_commands,
        # The discipline module is transfered along with its inputs,
        # but it is not used by itself.
        transfer_input_names=["in_file", "discipline"],
        transfer_output_names=["out_file"],
    )

    data = remote_disc.execute(
        {
            "in_file": str(in_path),
            "discipline": str(CURRENT_DIR_PATH / "discipline.py"),
        },
    )

    out_file_path = Path(data["out_file"])
    assert out_file_path.exists()
    assert int(out_file_path.read_text("utf8")) == 1


@pytest.mark.parametrize("compute_all_jacobians", [False, True])
@pytest.mark.parametrize("execute", [False, True])
def test_linearize(tmp_path, remote_setup, compute_all_jacobians, execute) -> None:
    """Test the linearization of the wrapped discipline."""

    local_disc = create_discipline("SobieskiMission")
    pre_commands = [remote_setup.activation_cmd]
    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        tmp_path,
        HOSTNAME,
        remote_workdir_path=remote_setup.workdir_path.as_posix(),
        pre_commands=pre_commands,
    )

    if not compute_all_jacobians:
        remote_disc.add_differentiated_inputs(["x_shared"])
        remote_disc.add_differentiated_outputs(["y_4"])
        local_disc.add_differentiated_inputs(["x_shared"])
        local_disc.add_differentiated_outputs(["y_4"])

    remote_disc.linearize(compute_all_jacobians=compute_all_jacobians, execute=execute)
    local_disc.linearize(compute_all_jacobians=compute_all_jacobians, execute=execute)

    data = remote_disc.jac
    assert "y_4" in data
    assert compare_dict_of_arrays(data, local_disc.jac)


def test_linearize_at_exe(tmp_path, remote_setup) -> None:
    """Test the linearization at execute."""

    # This discipline linearizes at exe
    local_disc = VolumeFraction()
    pre_commands = [remote_setup.activation_cmd]

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        tmp_path,
        HOSTNAME,
        remote_workdir_path=remote_setup.workdir_path.as_posix(),
        pre_commands=pre_commands,
    )

    remote_disc.execute()
    local_disc.execute()

    data = remote_disc.jac
    assert "volume fraction" in data
    assert compare_dict_of_arrays(data, local_disc.jac)
