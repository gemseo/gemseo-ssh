from __future__ import annotations

import getpass
import os
from pathlib import Path

from gemseo.api import create_discipline
from gemseo_ssh.problems.dummy_disc_with_files import DiscWithFiles
from gemseo_ssh.wrappers.ssh.api import wrap_discipline
from gemseo_ssh.wrappers.ssh.ssh_wrapped_disc import SSHDisciplineWrapper
from numpy import array

USERNAME = getpass.getuser()
HOME_DIR = Path(os.path.expanduser("~"))


def test_ssh_bliss(tmpdir):
    """Test the remote execution on a Linux env."""
    hostname = "bliss-2"
    port = 22
    key = str(HOME_DIR / ".ssh" / "id_rsa.pub")
    local_workdir = tmpdir
    distant_workdir = Path(f"/home/{USERNAME}/test_ssh").as_posix()
    authentification_method = SSHDisciplineWrapper.AUTHENTIFICATION_METHOD.public_key
    expression = {"b": "2*a"}
    analytic_disc = create_discipline("AnalyticDiscipline", expressions=expression)
    pre_commands = ["conda activate test_ssh"]
    new_disc = wrap_discipline(
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


def test_ssh_bliss_transfer(tmpdir):
    """Test the remote execution on a Linux env with files transfers."""
    hostname = "bliss-2"
    port = 22
    key = str(HOME_DIR / ".ssh" / "id_rsa.pub")
    local_workdir = tmpdir
    distant_workdir = Path(f"/home/{USERNAME}/test_ssh").as_posix()
    authentification_method = SSHDisciplineWrapper.AUTHENTIFICATION_METHOD.public_key
    discipline = DiscWithFiles(tmpdir)

    in_path = tmpdir / "in_f.txt"
    with open(in_path, "w") as infile:
        infile.write("0")

    pre_commands = ["conda activate test_ssh"]
    new_disc = wrap_discipline(
        discipline=discipline,
        local_workdir_path=local_workdir,
        hostname=hostname,
        port=port,
        username=USERNAME,
        password=None,
        ssh_public_key=key,
        authentification_method=authentification_method,
        distant_workdir_path=distant_workdir,
        pre_commands=pre_commands,
        transfer_inputs=["in_file"],
        transfer_outputs=["out_file"],
    )
    data = new_disc.execute({"in_file": str(in_path)})
    assert Path(data["out_file"]).exists()

    with open(data["out_file"]) as outfile:
        assert int(outfile.read()) == 1


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
    new_disc = wrap_discipline(
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
