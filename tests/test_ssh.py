from __future__ import annotations

from pathlib import Path

from gemseo.api import create_discipline
from gemseo_ssh.wrappers.ssh.api import wrap_discipline
from gemseo_ssh.wrappers.ssh.ssh_wrapped_disc import SSHDisciplineWrapper
from numpy import array


def test_ssh_bliss():
    """Test the remote execution on a Linux env."""
    hostname = "bliss-2"
    port = 22
    username = "jc.giret"
    key = "C:\\Users\\jc.giret\\.ssh\\id_rsa.pub"
    local_workdir = "C:\\Users\\jc.giret\\Documents\\test_ssh"
    distant_workdir = Path("/home/jc.giret/tmp_ssh").as_posix()
    authentification_method = SSHDisciplineWrapper.AUTHENTIFICATION_METHOD.public_key
    expression = {"b": "2*a"}
    analytic_disc = create_discipline("AnalyticDiscipline", expressions=expression)
    pre_commands = ["conda activate test_ssh"]
    new_disc = wrap_discipline(
        discipline=analytic_disc,
        local_workdir_path=local_workdir,
        hostname=hostname,
        port=port,
        username=username,
        password=None,
        ssh_public_key=key,
        authentification_method=authentification_method,
        distant_workdir_path=distant_workdir,
        pre_commands=pre_commands,
    )
    data = new_disc.execute({"a": array([1.0])})
    assert data["b"] == 2.0


def test_ssh_styx():
    """Test the execution on a Windows env."""
    hostname = "styx"
    port = 22
    username = "jc.giret"
    key = "C:\\Users\\jc.giret\\.ssh\\id_rsa.pub"
    local_workdir = "C:\\Users\\jc.giret\\Documents\\test_ssh"
    distant_workdir = Path("C:\\Users\\jc.giret\\test_ssh\\")
    authentification_method = SSHDisciplineWrapper.AUTHENTIFICATION_METHOD.public_key
    expression = {"b": "2*a"}
    pre_commands = [
        "C:\\Users\\jc.giret\\AppData\\Local\\miniconda3\\Scripts\\activate.bat",
        "conda activate test_ssh",
    ]
    analytic_disc = create_discipline("AnalyticDiscipline", expressions=expression)
    new_disc = wrap_discipline(
        discipline=analytic_disc,
        local_workdir_path=local_workdir,
        hostname=hostname,
        port=port,
        username=username,
        password=None,
        ssh_public_key=key,
        authentification_method=authentification_method,
        distant_workdir_path=distant_workdir,
        pre_commands=pre_commands,
    )
    data = new_disc.execute({"a": array([1.0])})
    assert data["b"] == 2.0
