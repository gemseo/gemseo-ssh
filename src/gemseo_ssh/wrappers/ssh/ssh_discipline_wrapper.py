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
"""Execution of a discipline on a remote host through SSH."""

from __future__ import annotations

from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from uuid import uuid1

import rpyc
from gemseo.core.discipline.discipline import Discipline

if TYPE_CHECKING:
    from collections.abc import Iterable

    from gemseo.typing import StrKeyMapping


LOGGER = getLogger(__name__)


class SSHDisciplineWrapper(Discipline):
    """A discipline to execute another discipline via ssh.

    The discipline is serialized to the disk, its input too, then a job file is created
    from a template to execute it with the provided options. The submission command is
    launched, it will setup the environment, deserialize the discipline and its inputs,
    execute it and serialize the outputs. Finally, the deserialized outputs are returned
    by the wrapper.
    """

    __conn: rpyc.Connection

    __discipline: Discipline
    """The discipline to execute on the remote host."""

    __local_root_wd_path: Path
    """The path to the root work directory on the local host."""

    __hostname: str
    """The name of the remote host to delegate the execution."""

    __remote_root_wd_path: Path
    """The path to the root work directory on the remote host."""

    __remote_cwd_path: Path
    """The path to the work directory on the remote host."""

    __inputs_to_upload: Iterable[str]
    """The names of the discipline inputs that correspond to files that must be
    uploaded before execution."""

    __outputs_to_download: Iterable[str]
    """The names of the discipline outputs that correspond to files that must be
    downloaded after execution."""

    __ssh_client_parameters: dict[str, Any]
    """The optional parameters for paramiko.SSHClient."""

    def __init__(
        self,
        discipline: Discipline,
        local_workdir_path: str | Path,
        hostname: str,
        remote_workdir_path: str | Path = "",
        inputs_to_upload: Iterable[str] = (),
        outputs_to_download: Iterable[str] = (),
        **ssh_client_parameters: Any,
    ) -> None:
        """
        Args:
            discipline: The discipline to wrap and execute on the remote host.
            local_workdir_path: The path to the work directory on the local host.
            username: The user name on the remote host.
            remote_workdir_path: The path to the work directory on the remote host.
                If empty, use the default ssh remote directory (usually user's home).
            inputs_to_upload: The names of the discipline inputs that correspond
                to files that must be uploaded before execution.
            outputs_to_download: The names of the discipline outputs that correspond
                to files that must be downloaded after execution.
            **ssh_client_parameters: The optional parameters to pass to
                paramiko.SSHClient.

        Raises:
            KeyError: if the inputs_to_upload or outputs_to_download arguments
                are inconsistent with the discipline grammars.
        """  # noqa: D205, D212, D415
        super().__init__(discipline.name)

        self.input_grammar = discipline.input_grammar
        self.output_grammar = discipline.output_grammar

        self.__discipline = discipline
        self.__local_root_wd_path = Path(local_workdir_path)
        self.__hostname = hostname
        self.__remote_root_wd_path = Path(remote_workdir_path)
        self.__set_io_to_transfer(inputs_to_upload, outputs_to_download)
        self.__ssh_client_parameters = ssh_client_parameters

    def __set_io_to_transfer(
        self,
        inputs_to_upload: Iterable[str],
        outputs_to_download: Iterable[str],
    ) -> None:
        """Set the inputs and outputs to upload and download.

        Args:
            inputs_to_upload: The names of the inputs to upload.
            outputs_to_download: The names of the outputs to download.

        Raises:
            ValueError: If a name is not in the corresponding grammar.
        """
        missing_in = set(inputs_to_upload).difference(self.input_grammar)
        if missing_in:
            msg = f"Invalid input names to upload: {', '.join(missing_in)}"
            raise ValueError(msg)

        self.__inputs_to_upload = inputs_to_upload

        missing_out = set(outputs_to_download).difference(self.output_grammar)
        if missing_out:
            msg = f"Invalid output names to download: {', '.join(missing_out)}"
            raise ValueError(msg)

        self.__outputs_to_download = outputs_to_download

    def _upload_inputs(self) -> None:
        """Send the input files to the remote host."""
        for data_name in self.__inputs_to_upload:
            local_path = Path(self.io.data[data_name])
            rpyc.classic.upload_file(self.__conn, local_path, local_path.name)

    def _download_outputs(self) -> None:
        """Retrieve the output files to the remote host after execution."""
        output_data = self.io.data
        for data_name in self.__outputs_to_download:
            file_name = Path(output_data[data_name]).name
            local_path = self.__local_root_wd_path / file_name
            output_data[data_name] = local_path.as_posix()
            rpyc.classic.download_file(self.__conn, file_name, local_path)

    def __create_cwd_paths(self) -> None:
        """Create the unique current local and remote work directory paths."""
        dir_name = str(uuid1()).split("-")[0]
        self.__local_cwd_path = self.__local_root_wd_path / dir_name
        self.__local_cwd_path.mkdir()
        self.__remote_cwd_path = self.__remote_root_wd_path / dir_name
        self.__conn.modules.os.mkdir(self.__remote_cwd_path)

    def _run(self, input_data: StrKeyMapping) -> StrKeyMapping:
        self.__conn = conn = rpyc.classic.connect("localhost")
        rpyc.utils.classic.redirected_stdio(conn)
        self.__create_cwd_paths()
        conn.modules.os.chdir(self.__remote_cwd_path)
        conn.modules.sys.path.append(str(self.__remote_cwd_path))
        self._upload_inputs()
        disc = rpyc.utils.classic.deliver(conn, self.__discipline)
        disc.io.data = rpyc.utils.classic.deliver(conn, self.io.data)
        disc._execute()
        self.io.data = rpyc.utils.classic.obtain(disc.io.data)
        self.jac = rpyc.utils.classic.obtain(disc.jac)
        self._has_jacobian = disc._has_jacobian
        self._download_outputs()
        LOGGER.debug("Job execution ended in %s", self.__local_cwd_path)
        return self.io.data

    def _compute_jacobian(
        self,
        input_names: Iterable[str] = (),
        output_names: Iterable[str] = (),
    ) -> None:
        self.__conn = conn = rpyc.classic.connect("localhost")
        self.__create_cwd_paths()
        conn.modules.os.chdir(self.__remote_cwd_path)
        conn.modules.sys.path.append(str(self.__remote_cwd_path))
        self._upload_inputs()
        disc = rpyc.utils.classic.deliver(conn, self.__discipline)
        disc.io.data = rpyc.utils.classic.deliver(conn, self.io.data)
        disc._compute_jacobian(input_names, output_names)
        self.io.data = rpyc.utils.classic.obtain(disc.io.data)
        self.jac = rpyc.utils.classic.obtain(disc.jac)
        self._has_jacobian = disc._has_jacobian
        self._download_outputs()
        LOGGER.debug("Job execution ended in %s", self.__local_cwd_path)
        return self.io.data
