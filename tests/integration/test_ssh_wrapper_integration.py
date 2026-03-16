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

"""Integration tests for SSHDisciplineWrapper with real SSH server."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from gemseo import create_discipline
from gemseo.core.grammars.simpler_grammar import SimplerGrammar

from gemseo_ssh import wrap_discipline_with_ssh
from gemseo_ssh.wrappers.ssh.ssh_discipline_wrapper import SSHDisciplineWrapper


@pytest.fixture
def ssh_connection_params(ssh_container):
    """Get connection parameters for the SSH container."""
    return ssh_container.get_connection_params()


@pytest.fixture
def disc_with_files_class(monkeypatch):
    """Import DiscWithFiles with proper sys.path setup."""
    monkeypatch.syspath_prepend(Path(__file__).parent.parent)
    from disc_with_files import DiscWithFiles

    return DiscWithFiles


def test_simple_discipline_execution(ssh_connection_params, tmp_path, remote_temp_dir):
    """Test basic discipline execution over SSH."""
    local_disc = create_discipline("SobieskiMission")

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        **ssh_connection_params,
    )

    result = remote_disc.execute()
    local_result = local_disc.execute()

    assert "y_4" in result
    for key in local_result:
        assert key in result


def test_linearization(ssh_connection_params, tmp_path, remote_temp_dir):
    """Test discipline linearization over SSH."""
    local_disc = create_discipline("SobieskiMission")

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        **ssh_connection_params,
    )

    remote_disc.add_differentiated_inputs(["x_shared"])
    remote_disc.add_differentiated_outputs(["y_4"])
    local_disc.add_differentiated_inputs(["x_shared"])
    local_disc.add_differentiated_outputs(["y_4"])

    remote_disc.linearize(execute=True)
    local_disc.linearize(execute=True)

    assert "y_4" in remote_disc.jac
    for out_key in local_disc.jac:
        assert out_key in remote_disc.jac


def test_copy_grammars_execution(ssh_connection_params, tmp_path, remote_temp_dir):
    """Test copy_grammars=True preserves grammar types and execution works."""
    local_disc = create_discipline("SobieskiMission")

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        copy_grammars=True,
        **ssh_connection_params,
    )

    # Grammars should be copies of the original, not SimplerGrammar
    assert not isinstance(remote_disc.input_grammar, SimplerGrammar)
    assert not isinstance(remote_disc.output_grammar, SimplerGrammar)
    assert type(remote_disc.input_grammar) is type(local_disc.input_grammar)
    assert type(remote_disc.output_grammar) is type(local_disc.output_grammar)

    result = remote_disc.execute()
    assert "y_4" in result


def test_linearize_without_execute(ssh_connection_params, tmp_path, remote_temp_dir):
    """Test linearize(execute=False) branch."""
    local_disc = create_discipline("SobieskiMission")

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        **ssh_connection_params,
    )

    remote_disc.add_differentiated_inputs(["x_shared"])
    remote_disc.add_differentiated_outputs(["y_4"])

    # execute=False triggers the 264->267 False branch
    remote_disc.linearize(execute=False)

    assert "y_4" in remote_disc.jac


def test_invalid_inputs_to_upload_raises(ssh_connection_params, tmp_path):
    """Test ValueError for invalid inputs_to_upload."""
    local_disc = create_discipline("SobieskiMission")

    with pytest.raises(ValueError, match="Invalid input names to upload"):
        wrap_discipline_with_ssh(
            local_disc,
            local_workdir_path=tmp_path,
            inputs_to_upload=["nonexistent_input"],
            **ssh_connection_params,
        )


def test_invalid_outputs_to_download_raises(ssh_connection_params, tmp_path):
    """Test ValueError for invalid outputs_to_download."""
    local_disc = create_discipline("SobieskiMission")

    with pytest.raises(ValueError, match="Invalid output names to download"):
        wrap_discipline_with_ssh(
            local_disc,
            local_workdir_path=tmp_path,
            outputs_to_download=["nonexistent_output"],
            **ssh_connection_params,
        )


def test_execution_with_file_upload(
    disc_with_files_class,
    ssh_connection_params,
    tmp_path,
    remote_temp_dir,
):
    """Test discipline with inputs_to_upload and outputs_to_download."""
    local_disc = disc_with_files_class()

    # Create input file
    in_file = tmp_path / "input.txt"
    in_file.write_text("42")

    # Create a dummy discipline file (needed by DiscWithFiles)
    disc_file = tmp_path / "discipline.py"
    disc_file.write_text("# dummy")

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        inputs_to_upload=["in_file", "discipline"],
        outputs_to_download=["out_file"],
        **ssh_connection_params,
    )

    result = remote_disc.execute({
        "in_file": str(in_file),
        "discipline": str(disc_file),
    })

    # Verify output file was downloaded
    out_file_path = Path(result["out_file"])
    assert out_file_path.exists()
    assert int(out_file_path.read_text()) == 43  # 42 + 1


def test_execution_with_file_download(
    disc_with_files_class,
    ssh_connection_params,
    tmp_path,
    remote_temp_dir,
):
    """Test discipline with outputs_to_download."""
    local_disc = disc_with_files_class()

    in_file = tmp_path / "input.txt"
    in_file.write_text("100")

    disc_file = tmp_path / "disc.py"
    disc_file.write_text("")

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        inputs_to_upload=["in_file", "discipline"],
        outputs_to_download=["out_file"],
        **ssh_connection_params,
    )

    result = remote_disc.execute({
        "in_file": str(in_file),
        "discipline": str(disc_file),
    })

    # Verify the downloaded file is in a UUID subdirectory, not the root workdir
    out_path = Path(result["out_file"])
    assert out_path.parent != tmp_path
    assert out_path.parent.parent == tmp_path
    assert out_path.exists()
    assert str(tmp_path) in str(out_path)


def test_download_numeric_output(
    disc_with_files_class,
    ssh_connection_params,
    tmp_path,
    remote_temp_dir,
):
    """Test that numeric outputs are returned correctly."""
    disc = disc_with_files_class()
    in_file = tmp_path / "input.txt"
    in_file.write_text("0")

    disc_file = tmp_path / "disc.py"
    disc_file.write_text("")

    remote_disc = wrap_discipline_with_ssh(
        disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        inputs_to_upload=["in_file", "discipline"],
        outputs_to_download=["out_file"],
        **ssh_connection_params,
    )

    result = remote_disc.execute({
        "in_file": str(in_file),
        "discipline": str(disc_file),
    })

    # Verify output path is in a UUID subdirectory, not the root workdir
    out_path = Path(result["out_file"])
    assert out_path.is_absolute()
    assert out_path.parent != tmp_path
    assert out_path.parent.parent == tmp_path
    assert str(tmp_path) in str(out_path)
    assert out_path.exists()
    assert out_path.read_text() == "1"


def test_missing_outputs_file(ssh_connection_params, tmp_path, remote_temp_dir):
    """Test FileNotFoundError when output pickle is missing locally."""
    local_disc = create_discipline("SobieskiMission")

    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        **ssh_connection_params,
    )

    # Patch _download_serialized_files to be a no-op so the outputs file
    # is never downloaded, triggering the FileNotFoundError check.
    with (
        patch.object(
            SSHDisciplineWrapper,
            "_download_serialized_files",
            lambda self, sftp: None,
        ),
        pytest.raises(
            FileNotFoundError,
            match="Serialized discipline outputs file does not exist",
        ),
    ):
        remote_disc.execute()


def test_remote_exception_propagation(
    disc_with_files_class,
    ssh_connection_params,
    tmp_path,
    remote_temp_dir,
):
    """Test that exceptions raised on the remote host are re-raised locally."""
    local_disc = disc_with_files_class()

    # No inputs_to_upload: the in_file path won't exist on the remote,
    # so DiscWithFiles._run will raise FileNotFoundError.
    remote_disc = wrap_discipline_with_ssh(
        local_disc,
        local_workdir_path=tmp_path,
        remote_workdir_path=remote_temp_dir,
        **ssh_connection_params,
    )

    with pytest.raises(FileNotFoundError):
        remote_disc.execute({
            "in_file": "/nonexistent/path.txt",
            "discipline": "/nonexistent/disc.py",
        })
