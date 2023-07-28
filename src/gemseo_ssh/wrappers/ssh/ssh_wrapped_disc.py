# Copyright 2023 IRT Saint Exupéry, https://www.irt-saintexupery.com
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
import time
from logging import getLogger
from pathlib import Path
from typing import ClassVar
from typing import Iterable
from uuid import uuid1

from gemseo.core.discipline import MDODiscipline
from paramiko import AutoAddPolicy
from paramiko.client import SSHClient
from paramiko.sftp_client import SFTPClient
from paramiko.ssh_exception import AuthenticationException
from strenum import StrEnum

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

    class AuthenticationMethod(StrEnum):
        """The ssh authentication method."""

        PASSWORD = "password"
        PUBLIC_KEY = "public_key"

    discipline: MDODiscipline
    """The discipline to execute on the remote host."""

    __pickled_discipline: bytes
    """The pickle object of the discipline."""

    __local_root_wd_path: Path
    """The path to the root work directory on the local host."""

    __hostname: str
    """The name of the remote host to delegate the execution."""

    __port: int
    """The port to use for SSH."""

    __username: str
    """The user name on the remote host."""

    __password: str
    """The password associated to the username on the remote host."""

    __ssh_public_key_path: Path
    """The path to the public key used for authentication on the remote host."""

    __authentication_method: AuthenticationMethod
    """The method used for authentication on the remote host."""

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

    def __init__(
        self,
        discipline: MDODiscipline,
        local_workdir_path: str | Path,
        hostname: str,
        port: int = 22,
        username: str = "",
        password: str = "",
        ssh_public_key_path: str | Path = "",
        authentication_method: AuthenticationMethod = AuthenticationMethod.PASSWORD,
        remote_workdir_path: str | Path = "",
        pre_commands: Iterable[str] = (),
        transfer_input_names: Iterable[str] = (),
        transfer_output_names: Iterable[str] = (),
    ) -> None:
        """
        Args:
            discipline: The discipline to wrap and execute on the remote host.
            local_workdir_path: The path to the work directory on the local host.
            hostname: The name of the remote host to delegate the execution.
            port: The port to use for SSH.
            username: The user name on the remote host.
            password: The password associated to the username on the remote host.
                Used when the authentication_method is
                SSHDisciplineWrapper.AuthenticationMethod.PASSWORD
            ssh_public_key_path: The path to the public key used for authentication on
                the remote host.
                Used when the authentication_method is
                SSHDisciplineWrapper.AuthenticationMethod.PUBLIC_KEY
            authentication_method: The method used for authentication on the remote host.
                Either public keys must be setup, or the plain password.
            remote_workdir_path: The path to the work directory on the remote host.
            pre_commands: The commands run on the remote host before deserialization and
                execution of the discipline on the remote host. This can be used to activate
                the Python environment for instance.
            transfer_input_names: The names of the discipline inputs that correspond
                to files that must be transferred before execution.
            transfer_output_names: The names of the discipline outputs that correspond
                to files that must be transferred after execution.

        Raises:
            KeyError: if the transfer_input_names or transfer_output_names arguments
                are inconsistent with the discipline grammars.
        """  # noqa: D205, D212, D415
        super().__init__(discipline.name, grammar_type=discipline.grammar_type)

        self.discipline = discipline
        self.input_grammar = self.discipline.input_grammar
        self.output_grammar = self.discipline.output_grammar
        self.default_inputs = self.discipline.default_inputs

        self.__local_root_wd_path = Path(local_workdir_path)
        self.__pickled_discipline = pickle.dumps(self.discipline)
        self.__pre_commands = pre_commands
        self.__hostname = hostname
        self.__port = port
        self.__username = username
        self.__password = password
        self.__ssh_public_key_path = Path(ssh_public_key_path)
        self.__remote_root_wd_path = Path(remote_workdir_path)
        self.__set_authentication_method(authentication_method)
        self.__set_transfer_io_names(transfer_input_names, transfer_output_names)

    def __set_transfer_io_names(
        self, transfer_input_names: Iterable[str], transfer_output_names: Iterable[str]
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
            raise ValueError(f"Invalid transfer_input_names: {missing_in}")

        self.__transfer_input_names = transfer_input_names

        missing_out = set(transfer_output_names) - self.output_grammar.keys()
        if missing_out:
            raise ValueError(f"Invalid transfer_output_names: {missing_out}")

        self.__transfer_output_names = transfer_output_names

    def __set_authentication_method(
        self, authentication_method: AuthenticationMethod
    ) -> None:
        """Check and set the authentication method.

        Args:
            authentication_method: The authentication method.

        Raises:
            ValueError: If the authentication method is inconsistent
                with the given parameters.
        """
        if (
            authentication_method == self.AuthenticationMethod.PASSWORD
            and not self.__password
        ):
            raise ValueError(
                "Password is not set while using password authentication for SSH connection."
            )

        if (
            authentication_method == self.AuthenticationMethod.PUBLIC_KEY
            and not self.__ssh_public_key_path
        ):
            raise ValueError(
                "SSH public key is not set while using public key authentication"
                " for SSH connection."
            )

        self.__authentication_method = authentication_method

    def _create_ssh_session(self) -> tuple[SSHClient, SFTPClient]:
        """Create a SSH session and the remote current workdir.

        Retuns:
            The SSH and SFTP clients.
        """
        ssh_client = SSHClient()
        ssh_client.set_missing_host_key_policy(AutoAddPolicy())

        key_filename = None

        if self.__authentication_method == self.AuthenticationMethod.PUBLIC_KEY:
            ssh_client.load_system_host_keys()
            key_filename = str(self.__ssh_public_key_path)

        try:
            ssh_client.connect(
                self.__hostname,
                self.__port,
                self.__username,
                allow_agent=False,
                key_filename=key_filename,
            )
        except AuthenticationException:
            raise AuthenticationException(
                "The authentication failed. Check your password or your ssh key."
            )

        ssh_client.get_transport().set_keepalive(self.SSH_KEEP_ALIVE_INTERVAL)
        LOGGER.debug(
            "Setting keep alive interval to %s seconds.", self.SSH_KEEP_ALIVE_INTERVAL
        )

        ftp_client = ssh_client.open_sftp()
        ftp_client.mkdir(str(self.__remote_cwd_path))
        ftp_client.chdir(str(self.__remote_cwd_path))

        return ssh_client, ftp_client

    def _send_serialized_files(
        self, ftp_client: SFTPClient, discipline_path: Path, input_path: Path
    ) -> None:
        """Sends the serialized inputs to the remote host.

        Args:
            ftp_client: The FTP client.
            discipline_path: The path to the serialized discipline.
            input_path: The path to the serialized inputs for execution.
        """
        start_time = time.time()
        ftp_client.put(
            localpath=str(discipline_path),
            remotepath=self.SERIALIZED_DISC_FILE_NAME,
            confirm=True,
        )
        ftp_client.put(
            localpath=str(input_path),
            remotepath=self.SERIALIZED_INPUTS_FILE_NAME,
            confirm=True,
        )
        LOGGER.debug(
            "Transfered serialized inputs to remote in %s seconds.",
            time.time() - start_time,
        )

    def _send_transfer_inputs(self, ftp_client: SFTPClient) -> None:
        """Sends the input files to the remote host before execution.

        Args:
            ftp_client: The FTP client.
        """
        for data_name in self.__transfer_input_names:
            start_time = time.time()
            local_path = Path(self.local_data[data_name])
            if not local_path.exists():
                raise FileNotFoundError(
                    f"Input to transfer {data_name} is not a file or does not exist!"
                )
            ftp_client.put(
                localpath=str(local_path),
                remotepath=local_path.name,
                confirm=True,
            )
            LOGGER.debug(
                "Transfered %s in %s seconds.",
                local_path,
                time.time() - start_time,
            )

    def _retrieve_serialized_outputs(
        self,
        ftp_client: SFTPClient,
    ) -> None:
        """Retrieves the output data to the remote host after execution.

        Args:
            ftp_client: The FTP client.
        """
        start_time = time.time()
        ftp_client.get(
            remotepath=str(self.SERIALIZED_OUTPUTS_FILE_NAME),
            localpath=self.__local_cwd_path / self.SERIALIZED_OUTPUTS_FILE_NAME,
        )
        LOGGER.debug(
            "Transfered serialized outputs from remote in %s seconds.",
            time.time() - start_time,
        )

    def _retrieve_transfer_outputs(self, ftp_client: SFTPClient) -> None:
        """Retrieves the output files to the remote host after execution.

        Args:
            ftp_client: The FTP client.
        """
        for data_name in self.__transfer_output_names:
            start_time = time.time()
            file_name = Path(self.local_data[data_name]).name
            local_path = str(self.__local_root_wd_path / file_name)
            ftp_client.get(remotepath=file_name, localpath=local_path)
            LOGGER.debug(
                "Transfered input file %s to remote in %s seconds.",
                local_path,
                time.time() - start_time,
            )
            self.local_data[data_name] = local_path

    def _execute_on_remote(self, ssh_client: SSHClient) -> None:
        """Executes the gemseo-deserialize-run command on the remote host.

        Args:
            ssh_client: The SSH client.
        """
        start_time = time.time()

        cmd_lines = [f"cd {self.__remote_cwd_path}"] + list(self.__pre_commands)
        cmd_lines += [
            f"gemseo-deserialize-run {self.__remote_cwd_path}"
            f" {self.SERIALIZED_DISC_FILE_NAME} {self.SERIALIZED_INPUTS_FILE_NAME}"
            f" {self.SERIALIZED_OUTPUTS_FILE_NAME}"
        ]

        cmd = " && ".join(cmd_lines)

        LOGGER.debug("Commands = %s ", cmd)
        stdin, f_stdout, f_stderr = ssh_client.exec_command(cmd)

        try:
            stdout = " ".join(f_stdout.readlines())
            stderr = " ".join(f_stderr.readlines())
        except Exception:
            stdout = "stdout not decoded"
            stderr = "stderr not decoded"

        return_code = f_stdout.channel.recv_exit_status()
        if return_code != 0:
            raise RuntimeError(
                f"Remote execution failed.\n"
                f"Distant command was: {cmd}\n"
                f"Return code is {return_code}.\n"
                f"stdout is {stdout}.\n"
                f"stderr is {stderr}."
            )

        LOGGER.debug(
            "Remote discipline execution in %s seconds.", time.time() - start_time
        )

    def _handle_outputs(self) -> None:
        """Deserializes the output data and updates the discipline's local data."""
        outputs_path = self.__local_cwd_path / self.SERIALIZED_OUTPUTS_FILE_NAME
        if not outputs_path.exists():
            raise FileNotFoundError(
                f"Serialized discipline outputs file does not exist {outputs_path}."
            )

        with outputs_path.open("rb") as output_file:
            output_data = pickle.load(output_file)

        if isinstance(output_data, tuple):
            error, trace = output_data
            LOGGER.error(
                "Discipline %s execution failed in %s",
                self.discipline.name,
                self.__local_cwd_path,
            )

            LOGGER.error(trace)
            raise error

        LOGGER.debug(
            "Discipline %s execution succeded in %s",
            self.discipline.name,
            self.__local_cwd_path,
        )

        self.local_data.update(output_data)

    def __create_cwd_paths(self) -> None:
        """Create the unique current local and remote work directory paths."""
        dir_name = str(uuid1()).split("-")[0]
        self.__local_cwd_path = self.__local_root_wd_path / dir_name
        self.__remote_cwd_path = self.__remote_root_wd_path / dir_name

    def _write_serialized_files(self) -> tuple[Path, Path]:
        """Serializes the files needed for the remote execution.

        Returns:
            The path to the serialized discipline, and the path to the serialized inputs.
        """
        self.__local_cwd_path.mkdir()

        discipline_path = self.__local_cwd_path / self.SERIALIZED_DISC_FILE_NAME
        discipline_path.write_bytes(self.__pickled_discipline)

        if self.__transfer_input_names:
            local_data = self.local_data.copy()
            for data_name in self.__transfer_input_names:
                local_path = Path(self.local_data[data_name])
                local_data[data_name] = str(self.__remote_cwd_path / local_path.name)
        else:
            local_data = self.local_data

        inputs_path = self.__local_cwd_path / self.SERIALIZED_INPUTS_FILE_NAME
        inputs_path.write_bytes(pickle.dumps(local_data))

        return discipline_path, inputs_path

    def _run(self) -> None:
        self.__create_cwd_paths()
        discipline_path, input_path = self._write_serialized_files()

        ssh_client, ftp_client = self._create_ssh_session()

        self._send_serialized_files(ftp_client, discipline_path, input_path)
        self._send_transfer_inputs(ftp_client)
        self._execute_on_remote(ssh_client)
        self._retrieve_serialized_outputs(ftp_client)
        self._handle_outputs()
        self._retrieve_transfer_outputs(ftp_client)

        ssh_client.close()

        LOGGER.debug("Job execution ended in %s", self.__local_cwd_path)
