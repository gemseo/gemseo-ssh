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

import pickle
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar
from uuid import uuid4

from gemseo.core.discipline import MDODiscipline

from gemseo_ssh.wrappers.ssh.paramiko import SFTPClient
from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

if TYPE_CHECKING:
    from collections.abc import Iterable


LOGGER = getLogger(__name__)


class SSHDisciplineWrapper(MDODiscipline):
    """A discipline to execute another discipline via ssh.

    The discipline is serialized to the disk, its input too, then a job file is created
    from a template to execute it with the provided options. The submission command is
    launched, it will setup the environment, deserialize the discipline and its inputs,
    execute it and serialize the outputs. Finally, the deserialized outputs are returned
    by the wrapper.
    """

    SERIALIZED_DISC_FILE_NAME: ClassVar[str] = "discipline.pckl"
    """The name of the file with the serialized discipline."""

    SERIALIZED_INPUTS_FILE_NAME: ClassVar[str] = "input_data.pckl"
    """The name of the file with the serialized discipline input data."""

    SERIALIZED_OUTPUTS_FILE_NAME: ClassVar[str] = "output_data.pckl"
    """The name of the file with the serialized discipline output data."""

    SSH_KEEP_ALIVE_INTERVAL: ClassVar[int] = 600
    """The time interval in seconds to keep the alive the ssh connection."""

    __discipline: MDODiscipline
    """The discipline to execute on the remote host."""

    __local_root_wd_path: Path
    """The path to the root work directory on the local host."""

    __hostname: str
    """The name of the remote host to delegate the execution."""

    __remote_root_wd_path: Path
    """The path to the root work directory on the remote host."""

    __remote_cwd_path: Path
    """The path to the work directory on the remote host."""

    __pre_commands: Iterable[str]
    """The commands run on the remote host before deserialization and execution of the
    discipline on the remote host."""

    __transfer_input_names: Iterable[str]
    """The names of the discipline inputs that correspond to files that must be
    transferred before execution."""

    __transfer_output_names: Iterable[str]
    """The names of the discipline outputs that correspond to files that must be
    transferred after execution."""

    __ssh_client_parameters: dict[str, Any]
    """The optional parameters for paramiko.SSHClient."""

    def __init__(
        self,
        discipline: MDODiscipline,
        local_workdir_path: str | Path,
        hostname: str,
        remote_workdir_path: str | Path = "",
        pre_commands: Iterable[str] = (),
        transfer_input_names: Iterable[str] = (),
        transfer_output_names: Iterable[str] = (),
        **ssh_client_parameters: Any,
    ) -> None:
        """
        Args:
            discipline: The discipline to wrap and execute on the remote host.
            local_workdir_path: The path to the work directory on the local host.
            username: The user name on the remote host.
            remote_workdir_path: The path to the work directory on the remote host.
                If empty, use the default ssh remote directory (usually user's home).
            pre_commands: The commands run on the remote host before deserialization and
                execution of the discipline on the remote host.
                This can be used to activate the Python environment for instance.
            transfer_input_names: The names of the discipline inputs that correspond
                to files that must be transferred before execution.
            transfer_output_names: The names of the discipline outputs that correspond
                to files that must be transferred after execution.
            **ssh_client_parameters: The optional parameters to pass to
                paramiko.SSHClient.

        Raises:
            KeyError: if the transfer_input_names or transfer_output_names arguments
                are inconsistent with the discipline grammars.
        """  # noqa: D205, D212, D415
        super().__init__(discipline.name, grammar_type=discipline.grammar_type)

        self.input_grammar = discipline.input_grammar
        self.output_grammar = discipline.output_grammar
        self.default_inputs = discipline.default_inputs

        self.__discipline = discipline
        self.__local_root_wd_path = Path(local_workdir_path)
        self.__pre_commands = pre_commands
        self.__hostname = hostname
        self.__remote_root_wd_path = Path(remote_workdir_path)
        self.__set_transfer_io_names(transfer_input_names, transfer_output_names)
        self.__ssh_client_parameters = ssh_client_parameters

    def __set_transfer_io_names(
        self,
        transfer_input_names: Iterable[str],
        transfer_output_names: Iterable[str],
    ) -> None:
        """Check and set the transfer inputs and outputs names.

        Args:
            transfer_input_names: The names of the inputs to transfer.
            transfer_output_names: The names of the outputs to transfer.

        Raises:
            ValueError: If a name is not in the corresponding grammar.
        """
        missing_in = set(transfer_input_names) - self.input_grammar.keys()
        if missing_in:
            msg = f"Invalid transfer_input_names: {missing_in}"
            raise ValueError(msg)

        self.__transfer_input_names = transfer_input_names

        missing_out = set(transfer_output_names) - self.output_grammar.keys()
        if missing_out:
            msg = f"Invalid transfer_output_names: {missing_out}"
            raise ValueError(msg)

        self.__transfer_output_names = transfer_output_names

    def _send_serialized_files(
        self,
        sftp_client: SFTPClient,
        discipline_path: Path,
        input_path: Path,
    ) -> None:
        """Send the serialized inputs to the remote host.

        Args:
            sftp_client: The FTP client.
            discipline_path: The path to the serialized discipline.
            input_path: The path to the serialized inputs for execution.
        """
        sftp_client.put(discipline_path, self.SERIALIZED_DISC_FILE_NAME)
        sftp_client.put(input_path, self.SERIALIZED_INPUTS_FILE_NAME)

    def _send_transfer_inputs(self, sftp_client: SFTPClient) -> None:
        """Send the input files to the remote host.

        Args:
            sftp_client: The FTP client.
        """
        for data_name in self.__transfer_input_names:
            local_path = Path(self.local_data[data_name])
            sftp_client.put(local_path, local_path.name)

    def _retrieve_serialized_outputs(
        self,
        sftp_client: SFTPClient,
    ) -> None:
        """Retrieve the output data to the remote host after execution.

        Args:
            sftp_client: The FTP client.
        """
        sftp_client.get(
            self.SERIALIZED_OUTPUTS_FILE_NAME,
            self.__local_cwd_path / self.SERIALIZED_OUTPUTS_FILE_NAME,
        )

    def _retrieve_transfer_outputs(self, sftp_client: SFTPClient) -> None:
        """Retrieve the output files to the remote host after execution.

        Args:
            sftp_client: The FTP client.
        """
        for data_name in self.__transfer_output_names:
            file_name = Path(self.local_data[data_name]).name
            local_path = self.__local_root_wd_path / file_name
            self.local_data[data_name] = local_path.as_posix()
            sftp_client.get(file_name, local_path)

    def _execute_on_remote(self, ssh_client: SSHClient) -> None:
        """Execute the gemseo-deserialize-run command on the remote host.

        Args:
            ssh_client: The SSH client.
        """
        cmd_lines = [
            f"cd {self.__remote_cwd_path.as_posix()}",
            *list(self.__pre_commands),
            f"gemseo-deserialize-run {self.__remote_cwd_path.as_posix()}"
            f" {self.SERIALIZED_DISC_FILE_NAME} {self.SERIALIZED_INPUTS_FILE_NAME}"
            f" {self.SERIALIZED_OUTPUTS_FILE_NAME}",
        ]
        ssh_client.execute(cmd_lines)

    def _handle_outputs(self) -> None:
        """Deserialize the output data and updates the discipline's local data."""
        outputs_path = self.__local_cwd_path / self.SERIALIZED_OUTPUTS_FILE_NAME

        if not outputs_path.exists():
            msg = f"Serialized discipline outputs file does not exist {outputs_path}."
            raise FileNotFoundError(msg)

        with outputs_path.open("rb") as output_file:
            output_data = pickle.load(output_file)

        if isinstance(output_data, tuple):
            error, trace = output_data
            LOGGER.error(
                "Discipline %s execution failed in %s",
                self.__discipline.name,
                self.__local_cwd_path,
            )

            LOGGER.error(trace)
            raise error

        LOGGER.debug(
            "Discipline %s execution succeded in %s",
            self.__discipline.name,
            self.__local_cwd_path,
        )

        self.local_data.update(output_data)

    def __create_cwd_paths(self, sftp_client: SFTPClient) -> None:
        """Create the unique current local and remote work directory paths."""
        dir_name = str(uuid4()).split("-")[0]
        self.__local_cwd_path = self.__local_root_wd_path / dir_name
        self.__local_cwd_path.mkdir()
        self.__remote_cwd_path = self.__remote_root_wd_path / dir_name
        sftp_client.mkdir(self.__remote_cwd_path)

    def _write_serialized_files(self) -> tuple[Path, Path]:
        """Serialize the files needed for the remote execution.

        Returns:
            The path to the serialized discipline and the path to the serialized inputs.
        """
        discipline_path = self.__local_cwd_path / self.SERIALIZED_DISC_FILE_NAME
        discipline_path.write_bytes(pickle.dumps(self.__discipline))

        if self.__transfer_input_names:
            local_data = self.local_data.copy()
            for data_name in self.__transfer_input_names:
                local_path = Path(self.local_data[data_name])
                local_data[data_name] = (
                    self.__remote_cwd_path / local_path.name
                ).as_posix()
        else:
            local_data = self.local_data

        inputs_path = self.__local_cwd_path / self.SERIALIZED_INPUTS_FILE_NAME
        inputs_path.write_bytes(pickle.dumps(local_data))

        return discipline_path, inputs_path

    def _run(self) -> None:
        ssh_client = SSHClient.create_connection(
            self.__hostname,
            self.SSH_KEEP_ALIVE_INTERVAL,
            **self.__ssh_client_parameters,
        )

        sftp_client = ssh_client.open_sftp()
        self.__create_cwd_paths(sftp_client)
        serialized_disc_path, serialized_inputs_path = self._write_serialized_files()
        sftp_client.chdir(self.__remote_cwd_path)
        self._send_serialized_files(
            sftp_client, serialized_disc_path, serialized_inputs_path
        )
        self._send_transfer_inputs(sftp_client)
        self._execute_on_remote(ssh_client)
        self._retrieve_serialized_outputs(sftp_client)
        self._handle_outputs()
        self._retrieve_transfer_outputs(sftp_client)

        ssh_client.close()

        LOGGER.debug("Job execution ended in %s", self.__local_cwd_path)
