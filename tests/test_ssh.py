from __future__ import annotations

import getpass
import os
import socket
import subprocess
import venv
from pathlib import Path
from typing import NamedTuple

import pytest
from gemseo import create_discipline
from gemseo.utils.comparisons import compare_dict_of_arrays
from gemseo.utils.platform import PLATFORM_IS_WINDOWS
from gemseo_ssh import wrap_discipline_with_ssh
from gemseo_ssh.wrappers.ssh.ssh_wrapped_disc import SSHDisciplineWrapper
from numpy import array


USERNAME = getpass.getuser()
HOME_DIR = Path(os.path.expanduser("~"))
HOSTNAME = socket.gethostname()
SSH_PORT = 22
PASSWORD = ""
AUTHENTIFICATION_METHOD = SSHDisciplineWrapper.AuthentificationMethod.PUBLIC_KEY
CURRENT_DIR_PATH = Path(__file__).parent

if PLATFORM_IS_WINDOWS:
    VENV_REL_PATH_TO_PYTHON = "Scripts/python.exe"
    ACTIVATE_CMD = r"{venv_path}\Scripts\activate.ps1"
else:
    VENV_REL_PATH_TO_PYTHON = "bin/python"
    ACTIVATE_CMD = ". {venv_path}/bin/activate"


class RemoteSetup(NamedTuple):
    workdir_path: Path
    venv_path: Path
    activation_cmd: str


def test_helper_discipline(tmp_path, monkeypatch):
    """Test execution."""
    monkeypatch.syspath_prepend(CURRENT_DIR_PATH)
    from discipline import DiscWithFiles

    disc = DiscWithFiles()

    in_path = tmp_path / "in_f.txt"
    in_path.write_text("0")

    out = disc.execute(
        {
            "in_file": str(in_path),
            "discipline": "",
        }
    )
    assert out["out_val"] == 1

    assert Path(out["out_file"]).exists()


@pytest.fixture(scope="module")
def remote_setup(tmp_path_factory):
    """Create the virtual env for the remote connection on the local host."""
    workdir_path = tmp_path_factory.mktemp("ssh-workdir")
    workdir_path = Path('/tmp/test_ssh')
    venv_path = workdir_path / "venv"
    venv.create(venv_path, with_pip=True)
    subprocess.run(
        f"{venv_path / VENV_REL_PATH_TO_PYTHON} -m pip install gemseo".split(),
        check=True,
        capture_output=True,
    )
    return RemoteSetup(
        workdir_path, venv_path, ACTIVATE_CMD.format(venv_path=venv_path)
    )


def test_linux(tmp_path, remote_setup):
    """Test the remote execution on a Linux env."""
    key = str(HOME_DIR / ".ssh" / "id_rsa.pub")
    local_disc = create_discipline("SobieskiMission")
    pre_commands = [remote_setup.activation_cmd]

    remote_disc = wrap_discipline_with_ssh(
        discipline=local_disc,
        local_workdir_path=tmp_path,
        hostname=HOSTNAME,
        port=SSH_PORT,
        username=USERNAME,
        password=PASSWORD,
        ssh_public_key=key,
        authentification_method=AUTHENTIFICATION_METHOD,
        remote_workdir_path=remote_setup.workdir_path.as_posix(),
        pre_commands=pre_commands,
    )
    data = remote_disc.execute()

    ref_data = local_disc.execute()
    assert compare_dict_of_arrays(data, ref_data)


def test_linux_transfer(tmp_path, remote_setup, monkeypatch):
    """Test the remote execution on a Linux env with files transfers."""
    key = str(HOME_DIR / ".ssh" / "id_rsa.pub")

    # For the picling to work, the namespace of the discipline shall be accessible on the
    # remote host, this can be done by importing it absolutely the both on local and remote hosts.
    monkeypatch.syspath_prepend(CURRENT_DIR_PATH)
    from discipline import DiscWithFiles

    local_disc = DiscWithFiles()

    pre_commands = [
        remote_setup.activation_cmd,
        # This allows unpickling the discipline on the remote host.
        f"export PYTHONPATH={remote_setup.workdir_path}:$PYTHONPATH",
    ]

    in_path = tmp_path / "in_f.txt"
    in_path.write_text("0")

    remote_disc = wrap_discipline_with_ssh(
        discipline=local_disc,
        local_workdir_path=tmp_path,
        hostname=HOSTNAME,
        port=SSH_PORT,
        username=USERNAME,
        password=PASSWORD,
        ssh_public_key=key,
        authentification_method=AUTHENTIFICATION_METHOD,
        remote_workdir_path=remote_setup.workdir_path.as_posix(),
        pre_commands=pre_commands,
        # The discipline module is transfered along with its inputs, but it is not used by itself.
        transfer_inputs=["in_file", "discipline"],
        transfer_outputs=["out_file"],
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


def test_ssh_styx():
    """Test the execution on a Windows env."""
    hostname = "styx"
    port = 22
    key = f"C:\\Users\\{USERNAME}\\.ssh\\id_rsa.pub"
    local_workdir = f"C:\\Users\\{USERNAME}\\Documents\\test_ssh"
    distant_workdir = Path(f"C:\\Users\\{USERNAME}\\test_ssh\\")
    authentification_method = SSHDisciplineWrapper.AUTHENTIFICATION_METHOD.public_key
    expression = {"b": "2*a"}
    pre_commands = [
        f"C:\\Users\\{USERNAME}\\AppData\\Local\\miniconda3\\Scripts\\activate.bat",
        "conda activate test_ssh",
    ]
    analytic_disc = create_discipline("AnalyticDiscipline", expressions=expression)
    new_disc = wrap_discipline_with_ssh(
        discipline=analytic_disc,
        local_workdir_path=local_workdir,
        hostname=hostname,
        port=port,
        username=USERNAME,
        password=None,
        ssh_public_key=key,
        authentification_method=authentification_method,
        distant_workdir_path=distant_workdir,
        pre_commands=pre_commands,
    )
    data = new_disc.execute({"a": array([1.0])})
    assert data["b"] == 2.0
