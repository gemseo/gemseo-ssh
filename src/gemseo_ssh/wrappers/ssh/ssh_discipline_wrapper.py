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

from gemseo.core.discipline.discipline import Discipline
from gemseo.utils.constants import READ_ONLY_EMPTY_DICT
from gemseo.utils.directory_creator import DirectoryCreator
from gemseo.utils.directory_creator import DirectoryNamingMethod

from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import MutableMapping

    from gemseo.typing import JacobianData
    from gemseo.typing import StrKeyMapping

    from gemseo_ssh.wrappers.ssh.paramiko import SFTPClient


LOGGER = getLogger(__name__)


class SSHDisciplineWrapper(Discipline):
    """A discipline to execute another discipline via ssh.

    The discipline is serialized to the disk, its input too, then a job file is created
    from a template to execute it with the provided options. The submission command is
    launched, it will setup the environment, deserialize the discipline and its inputs,
    execute it and serialize the outputs. Finally, the deserialized outputs are returned
    by the wrapper.
    """

    default_grammar_type = Discipline.GrammarType.SIMPLER

    SERIALIZED_DISC_FILE_NAME: ClassVar[str] = "discipline.pckl"
    """The name of the file with the serialized discipline."""

    SERIALIZED_INPUTS_FILE_NAME: ClassVar[str] = "input_data.pckl"
    """The name of the file with the serialized discipline input data."""

    SERIALIZED_OUTPUTS_FILE_NAME: ClassVar[str] = "output_data.pckl"
    """The name of the file with the serialized discipline output data."""

    SSH_KEEP_ALIVE_INTERVAL: ClassVar[int] = 600
    """The time interval in seconds to keep the alive the ssh connection."""

    __execute_at_linearize: bool
    """Whether to execute the discipline at linearization."""

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

    __pre_commands: Iterable[str]
    """The commands run on the remote host before deserialization and execution of the
    discipline on the remote host."""

    __inputs_to_upload: Iterable[str]
    """The names of the discipline inputs that correspond to files that must be
    uploaded before execution."""

    __outputs_to_download: Iterable[str]
    """The names of the discipline outputs that correspond to files that must be
    downloaded after execution."""

    __ssh_client_parameters: dict[str, Any]
    """The optional parameters for paramiko.SSHClient."""

    __directory_creator: DirectoryCreator
    """The directory creator to create and generate unique folder names."""

    def __init__(
        self,
        discipline: Discipline,
        local_workdir_path: str | Path,
        hostname: str,
        remote_workdir_path: str | Path = "",
        pre_commands: Iterable[str] = (),
        inputs_to_upload: Iterable[str] = (),
        outputs_to_download: Iterable[str] = (),
        copy_grammars: bool = False,
        **ssh_client_parameters: Any,
    ) -> None:
        """
        Args:
            discipline: The discipline to wrap and execute on the remote host.
            local_workdir_path: The path to the work directory on the local host.
            hostname: The name of the remote host to delegate the execution.
            remote_workdir_path: The path to the work directory on the remote host.
                If empty, use the default ssh remote directory (usually user's home).
            pre_commands: The commands run on the remote host before deserialization and
                execution of the discipline on the remote host.
                This can be used to activate the Python environment for instance.
            inputs_to_upload: The names of the discipline inputs that correspond
                to files that must be uploaded before execution.
            outputs_to_download: The names of the discipline outputs that correspond
                to files that must be downloaded after execution.
            copy_grammars: Whether to copy the grammars from the wrapped discipline.
                Copying the grammars ensures that the inputs and outputs are verified
                with the same levels of strictness as in the original discipline.
                Otherwise, a :class:`.SimplerGrammar` is used, which only verifies
                the names of the inputs and outputs.
            **ssh_client_parameters: The optional parameters to pass to
                paramiko.SSHClient.

        Raises:
            KeyError: if the inputs_to_upload or outputs_to_download arguments
                are inconsistent with the discipline grammars.
        """  # noqa: D205, D212, D415
        super().__init__(discipline.name)

        if copy_grammars:
            self.input_grammar = discipline.input_grammar.copy()
            self.output_grammar = discipline.output_grammar.copy()
        else:
            self.input_grammar.update(discipline.input_grammar)
            self.output_grammar.update(discipline.output_grammar)

        self.__discipline = discipline
        self.__local_root_wd_path = Path(local_workdir_path)
        self.__pre_commands = pre_commands
        self.__hostname = hostname
        self.__remote_root_wd_path = Path(remote_workdir_path)
        self.__set_io_to_transfer(inputs_to_upload, outputs_to_download)
        self.__ssh_client_parameters = ssh_client_parameters
        self.__execute_at_linearize = False
        self.__directory_creator = DirectoryCreator(
            directory_naming_method=DirectoryNamingMethod.UUID,
            root_directory=Path(local_workdir_path),
        )

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

    def _upload_serialized_files(
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

    def _upload_inputs(self, sftp_client: SFTPClient) -> None:
        """Send the input files to the remote host.

        Args:
            sftp_client: The FTP client.
        """
        for data_name in self.__inputs_to_upload:
            local_path = Path(self.io.data[data_name])
            sftp_client.put(local_path, local_path.name)

    def _download_serialized_files(
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

    def _download_outputs(
        self,
        sftp_client: SFTPClient,
        output_data: MutableMapping[str, Any],
    ) -> None:
        """Retrieve the output files to the remote host after execution.

        Args:
            sftp_client: The FTP client.
        """
        for data_name in self.__outputs_to_download:
            file_name = Path(output_data[data_name]).name
            local_path = self.__local_cwd_path / file_name
            output_data[data_name] = local_path.as_posix()
            sftp_client.get(file_name, local_path)

    def _execute_on_remote(
        self,
        ssh_client: SSHClient,
        linearize: bool = False,
    ) -> None:
        """Execute the gemseo-deserialize-run command on the remote host.

        Args:
            ssh_client: The SSH client.
            linearize: wheather to linearize the discipline.
        """
        linearization_options = ""
        if linearize:
            linearization_options = "--linearize"
            if self.__execute_at_linearize:
                linearization_options += " --execute-at-linearize"

        cmd_lines = [
            f"cd {self.__remote_cwd_path.as_posix()}",
            *list(self.__pre_commands),
            (
                f"gemseo-deserialize-run"
                f" {self.SERIALIZED_DISC_FILE_NAME} {self.SERIALIZED_INPUTS_FILE_NAME}"
                f" {self.SERIALIZED_OUTPUTS_FILE_NAME} {linearization_options}"
            ),
        ]

        ssh_client.execute(cmd_lines)

    def _handle_outputs(self) -> StrKeyMapping:
        """Deserialize the output data and updates the discipline's local data."""
        outputs_path = self.__local_cwd_path / self.SERIALIZED_OUTPUTS_FILE_NAME

        if not outputs_path.exists():
            msg = f"Serialized discipline outputs file does not exist {outputs_path}."
            raise FileNotFoundError(msg)

        with outputs_path.open("rb") as output_file:
            output_data = pickle.load(output_file)

        if isinstance(output_data[0], BaseException):
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

        if output_data[1]:
            self.jac = output_data[1]

        return output_data[0]

    def _create_local_and_remote_directories(self, sftp_client: SFTPClient) -> None:
        """Create the unique current local and remote work directories.

        Args:
             sftp_client: The FTP client.
        """
        self.__local_cwd_path = self.__directory_creator.create()
        dir_name = self.__directory_creator.last_directory.name
        self.__remote_cwd_path = self.__remote_root_wd_path / dir_name
        sftp_client.mkdir(self.__remote_cwd_path)

    def _write_serialized_files(
        self,
        differentiated_inputs: Iterable[str] = (),
        differentiated_outputs: Iterable[str] = (),
    ) -> tuple[Path, Path]:
        """Serialize the files needed for the remote execution.

        Args:
            differentiated_inputs: If the linearization is performed, the
                inputs that define the rows of the jacobian.
            differentiated_outputs: If the linearization is performed, the
                outputs that define the columns of the jacobian.

        Returns:
            The path to the serialized discipline and the path to the serialized inputs.
        """
        discipline_path = self.__local_cwd_path / self.SERIALIZED_DISC_FILE_NAME
        discipline_path.write_bytes(pickle.dumps(self.__discipline))

        if self.__inputs_to_upload:
            local_data = self.io.data.copy()
            for data_name in self.__inputs_to_upload:
                local_path = Path(self.io.data[data_name])
                local_data[data_name] = (
                    self.__remote_cwd_path / local_path.name
                ).as_posix()
        else:
            local_data = self.io.data

        inputs_path = self.__local_cwd_path / self.SERIALIZED_INPUTS_FILE_NAME
        inputs_path.write_bytes(
            pickle.dumps((local_data, differentiated_inputs, differentiated_outputs))
        )

        return discipline_path, inputs_path

    def _run(self, input_data: StrKeyMapping) -> StrKeyMapping:
        return self._run_or_compute_jac(False)

    def linearize(  # noqa: D102
        self,
        input_data: StrKeyMapping = READ_ONLY_EMPTY_DICT,
        compute_all_jacobians: bool = False,
        execute: bool = True,
    ) -> JacobianData:
        self.__execute_at_linearize = execute
        return super().linearize(
            input_data=input_data,
            compute_all_jacobians=compute_all_jacobians,
            execute=False,
        )

    def _compute_jacobian(
        self,
        input_names: Iterable[str] = (),
        output_names: Iterable[str] = (),
    ) -> None:
        self._run_or_compute_jac(
            True, differentiated_inputs=input_names, differentiated_outputs=output_names
        )

    def _run_or_compute_jac(
        self,
        linearize: bool,
        differentiated_inputs: Iterable[str] = (),
        differentiated_outputs: Iterable[str] = (),
    ) -> None:
        """Executes or linearizes the discipline.

        Args:
            linearize: wheather to linearize the discipline.
            differentiated_inputs: If the linearization is performed, the
                inputs that define the rows of the jacobian.
            differentiated_outputs: If the linearization is performed, the
                outputs that define the columns of the jacobian.
        """
        ssh_client = SSHClient.create_connection(
            self.__hostname,
            self.SSH_KEEP_ALIVE_INTERVAL,
            **self.__ssh_client_parameters,
        )
        sftp_client = ssh_client.open_sftp()
        self._create_local_and_remote_directories(sftp_client)
        serialized_disc_path, serialized_inputs_path = self._write_serialized_files(
            differentiated_inputs, differentiated_outputs
        )
        sftp_client.chdir(self.__remote_cwd_path)
        self._upload_serialized_files(
            sftp_client, serialized_disc_path, serialized_inputs_path
        )
        self._upload_inputs(sftp_client)
        self._execute_on_remote(ssh_client, linearize)
        self._download_serialized_files(sftp_client)
        output_data = self._handle_outputs()
        self._download_outputs(sftp_client, output_data)

        ssh_client.close()

        LOGGER.debug("Job execution ended in %s", self.__local_cwd_path)
        return output_data
