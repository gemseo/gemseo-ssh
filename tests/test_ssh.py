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
from pathlib import PureWindowsPath
from typing import TYPE_CHECKING
from typing import NamedTuple
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from filelock import FileLock
from gemseo import create_discipline
from gemseo.disciplines.wrappers.job_schedulers.discipline_wrapper import (
    JobSchedulerDisciplineWrapper,
)
from gemseo.problems.topology_optimization.volume_fraction_disc import VolumeFraction
from gemseo.utils.comparisons import compare_dict_of_arrays
from gemseo.utils.platform import PLATFORM_IS_WINDOWS
from gemseo.utils.testing.pytest_conftest import tmp_wd  # noqa: F401

from gemseo_ssh import wrap_discipline_with_ssh

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gemseo.core.discipline.discipline import Discipline

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
    getcwd = os.getcwd


# def mock_execute(cmd_lines) -> None:
#     """Mock execute that runs commands locally like SSHClient.execute."""
#     cmd = " && ".join(cmd_lines)
#     os.system(cmd)


def mock_execute(cmd_lines: Sequence[str]) -> tuple:
    """Mock the related command of the ssh client."""
    cmd = " && ".join(cmd_lines)
    exit_code = os.system(cmd)
    stdout = MagicMock()
    stdout.channel.recv_exit_status = lambda: exit_code
    return None, stdout, MagicMock()


def create_mock_ssh_client_instance():
    """Create a mock SSH client instance with proper SFTP and execute behavior."""
    instance = MagicMock()
    instance.open_sftp = SFTP
    instance.execute = mock_execute
    return instance


MockParamikoSSHCLIENT = MagicMock()
MockParamikoSSHCLIENT.set_missing_host_key_policy = MagicMock()
MockParamikoSSHCLIENT.load_system_host_keys = MagicMock()
MockParamikoSSHCLIENT.connect = MagicMock()
MockParamikoSSHCLIENT.get_transport = MagicMock()

MockGemseoSSHClient = MagicMock()
MockGemseoSSHClient.create_connection = MagicMock(
    side_effect=lambda *args, **kwargs: create_mock_ssh_client_instance()
)


class RemoteSetup(NamedTuple):
    """Settings for the remote."""

    workdir_path: Path
    activation_cmd: str
    set_python_path_cmd: str


@patch("paramiko.SSHClient", MockParamikoSSHCLIENT)
@patch("gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient", MockGemseoSSHClient)
def test_helper_discipline(tmp_path):
    """Test execution."""
    from .disc_with_files import DiscWithFiles

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
    venv.create(path, with_pip=True, symlinks=True)

    gemseo_version = "gemseo[all]@git+https://gitlab.com/gemseo/dev/gemseo.git@develop"

    subprocess.run(
        f"{path / VENV_REL_PATH_TO_PYTHON} -m pip install {gemseo_version}".split(),
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
        SET_PYTHONPATH_CMD.format(workdir_path=CURRENT_DIR_PATH),
    )


@pytest.mark.parametrize("copy_grammars", [True, False])
@patch("gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient", MockGemseoSSHClient)
def test_execution(tmp_path, remote_setup, copy_grammars):
    """Test the remote execution."""
    local_disc = create_discipline("SobieskiMission")
    pre_commands = [remote_setup.activation_cmd]

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        tmp_path,
        HOSTNAME,
        remote_workdir_path=remote_setup.workdir_path.as_posix(),
        pre_commands=pre_commands,
        copy_grammars=copy_grammars,
    )

    data = remote_disc.execute()
    ref_data = local_disc.execute()
    assert compare_dict_of_arrays(data, ref_data)


@patch("gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient", MockGemseoSSHClient)
def test_execution_with_transfer(tmp_path, remote_setup, monkeypatch):
    """Test the remote execution with files transfers."""
    # For the pickling to work,
    # the namespace of the discipline shall be accessible on the
    # remote host, this can be done by importing it absolutely the both
    # on local and remote hosts.
    monkeypatch.syspath_prepend(CURRENT_DIR_PATH)
    from disc_with_files import DiscWithFiles

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
        # The discipline module is transferred along with its inputs,
        # but it is not used by itself.
        inputs_to_upload=["in_file", "discipline"],
        outputs_to_download=["out_file"],
    )

    data = remote_disc.execute(
        {
            "in_file": str(in_path),
            "discipline": str(CURRENT_DIR_PATH / "disc_with_files.py"),
        },
    )

    out_file_path = Path(data["out_file"])
    assert out_file_path.exists()
    assert int(out_file_path.read_text("utf8")) == 1


@patch("gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient", MockGemseoSSHClient)
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


@patch("gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient", MockGemseoSSHClient)
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


@patch("gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient", MockGemseoSSHClient)
def test_inputs_names_error(tmp_path):
    """Verify the error when the inputs_to_upload is bad."""
    msg = "Invalid input names to upload: bad-name"
    with pytest.raises(ValueError, match=msg):
        wrap_discipline_with_ssh(
            create_discipline("SobieskiMission"),
            tmp_path,
            HOSTNAME,
            inputs_to_upload=["bad-name"],
        )


@patch("gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient", MockGemseoSSHClient)
def test_outputs_names_error(tmp_path):
    """Verify the error when the outputs_to_upload is bad."""
    msg = "Invalid output names to download: .+-name, .+-name"
    with pytest.raises(ValueError, match=msg):
        wrap_discipline_with_ssh(
            create_discipline("SobieskiMission"),
            tmp_path,
            HOSTNAME,
            outputs_to_download=["bad-name", "ko-name"],
        )


class TestSSHClientCreateConnection:
    """Tests for SSHClient.create_connection edge cases."""

    @patch(
        "gemseo_ssh.wrappers.ssh.paramiko.SSHClient.get_transport", return_value=None
    )
    @patch("gemseo_ssh.wrappers.ssh.paramiko.SSHClient.connect")
    @patch("gemseo_ssh.wrappers.ssh.paramiko.SSHClient.load_system_host_keys")
    @patch("gemseo_ssh.wrappers.ssh.paramiko.SSHClient.set_missing_host_key_policy")
    def test_create_connection_no_transport(self, policy, keys, connect, transport):
        """Test that create_connection raises RuntimeError when transport is None."""
        from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

        with pytest.raises(RuntimeError, match="Cannot get the ssh transport"):
            SSHClient.create_connection("hostname", keep_alive_interval=60)


class TestSSHClientExecute:
    """Tests for SSHClient.execute edge cases."""

    def test_execute_undecodable_output(self):
        """Test execute when stdout/stderr readlines raises an exception."""
        from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

        client = SSHClient()

        stdout = MagicMock()
        stdout.readlines.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")
        stdout.channel.recv_exit_status.return_value = 1

        stderr = MagicMock()
        stderr.readlines.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")

        with patch.object(client, "exec_command", return_value=(None, stdout, stderr)):
            # Should not raise, but log an error with fallback messages.
            client.execute(["echo hello"])


@pytest.fixture(params=[True, False])
def discipline_mocked_js(tmp_wd, request) -> Discipline:  # noqa: F811
    """Creates either a SobieskiMission or a JobSchedulerDisciplineWrapper
     wrapping SobieskiMission.

    Returns:
        The wrapped discipline
    """
    disc = create_discipline("SobieskiMission")
    if request.param:
        return JobSchedulerDisciplineWrapper(
            discipline=disc,
            job_template_path=CURRENT_DIR_PATH / "mock_job_scheduler.py",
            workdir_path=tmp_wd,
            job_out_filename="run_disc.py",
            scheduler_run_command="python",
        )
    return disc


@patch("gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient", MockGemseoSSHClient)
@pytest.mark.parametrize("copy_grammars", [True, False])
@pytest.mark.parametrize("use_namespaces", [True, False])
def test_job_scheduler_discipline_wrapper(
    tmp_path,
    remote_setup,
    monkeypatch,
    discipline_mocked_js,
    use_namespaces,
    copy_grammars,
):
    """Test the SSHDiscipline with a Job Scheduler Discipline wrapped inside."""

    monkeypatch.syspath_prepend(CURRENT_DIR_PATH)

    pre_commands = [
        remote_setup.activation_cmd,
        # This allows unpickling the discipline on the remote host.
        remote_setup.set_python_path_cmd,
    ]

    remote_disc = wrap_discipline_with_ssh(
        discipline_mocked_js,
        tmp_path,
        HOSTNAME,
        remote_workdir_path=remote_setup.workdir_path.as_posix(),
        pre_commands=pre_commands,
        copy_grammars=copy_grammars,
    )

    if use_namespaces:
        remote_disc.input_grammar.add_namespace("y_14", "ns1")
        remote_disc.output_grammar.add_namespace("y_4", "ns1")

    data = remote_disc.execute()
    if use_namespaces:
        assert "ns1:y_4" in data
    else:
        assert "y_4" in data


class TestWindowsPathHandling:
    """Tests that path conversions always produce POSIX (forward-slash) strings.

    This verifies the `.as_posix()` contract in SFTPClient and SSHDisciplineWrapper
    when PureWindowsPath objects are involved.
    """

    def test_mkdir_converts_windows_path(self):
        """Test that SFTPClient.mkdir sends POSIX paths to the underlying SFTP."""
        from paramiko.sftp_client import SFTPClient as _SFTPClient

        from gemseo_ssh.wrappers.ssh.paramiko import SFTPClient

        sftp = MagicMock(spec=SFTPClient)
        sftp.stat.side_effect = OSError  # Force mkdir for each parent

        with patch.object(_SFTPClient, "mkdir") as parent_mkdir:
            SFTPClient.mkdir(sftp, PureWindowsPath("C:/Users/test/workdir/uuid"))

        assert parent_mkdir.call_count > 0
        created_paths = [call[0][0] for call in parent_mkdir.call_args_list]
        for path_str in created_paths:
            assert "\\" not in path_str, f"Backslash found in path: {path_str}"
        assert "C:/Users/test/workdir/uuid" in created_paths

    def test_chdir_converts_windows_path(self):
        """Test that SFTPClient.chdir sends a POSIX path to the underlying SFTP."""
        from paramiko.sftp_client import SFTPClient as _SFTPClient

        from gemseo_ssh.wrappers.ssh.paramiko import SFTPClient

        sftp = MagicMock(spec=SFTPClient)

        with patch.object(_SFTPClient, "chdir") as parent_chdir:
            SFTPClient.chdir(sftp, PureWindowsPath("C:\\Users\\test\\workdir"))

        parent_chdir.assert_called_once()
        path_str = parent_chdir.call_args[0][0]
        assert path_str == "C:/Users/test/workdir"
        assert "\\" not in path_str

    @patch(
        "gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper.SSHClient",
        MockGemseoSSHClient,
    )
    def test_execute_on_remote_uses_posix_paths(self, tmp_path):
        """Test that _execute_on_remote builds cd commands with forward slashes."""
        local_disc = create_discipline("SobieskiMission")

        wrapper = wrap_discipline_with_ssh(
            local_disc,
            tmp_path,
            HOSTNAME,
            remote_workdir_path="C:/Users/test/workdir",
        )

        # Simulate a PureWindowsPath for the remote current working directory.
        wrapper._SSHDisciplineWrapper__remote_cwd_path = PureWindowsPath(
            "C:\\Users\\test\\workdir\\some-uuid"
        )

        mock_ssh = MagicMock()
        wrapper._execute_on_remote(mock_ssh)

        cmd_lines = mock_ssh.execute.call_args[0][0]
        cd_cmd = cmd_lines[0]
        assert "C:/Users/test/workdir/some-uuid" in cd_cmd
        assert "\\" not in cd_cmd
