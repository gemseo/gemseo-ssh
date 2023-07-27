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
from typing import TYPE_CHECKING
from uuid import uuid1

from gemseo.core.discipline import MDODiscipline
from paramiko import AutoAddPolicy
from paramiko.client import SSHClient
from paramiko.sftp_client import SFTPClient
from paramiko.ssh_exception import AuthenticationException
from strenum import StrEnum

if TYPE_CHECKING:
    from typing import Sequence

LOGGER = getLogger(__name__)


class SSHDisciplineWrapper(MDODiscipline):
    """A discipline to execute another discipline via ssh.

    The discipline is serialized to the disk, its input too, then a job file is created
    from a template to execute it with the provided options. The submission command is
    launched, it will setup the environment, deserialize the discipline and its inputs,
    execute it and serialize the outputs. Finally, the deserialized outputs are returned
    by the wrapper.
    """

    DISC_PICKLE_FILE_NAME: ClassVar[str] = "discipline.pckl"
    DISC_INPUT_FILE_NAME: ClassVar[str] = "input_data.pckl"
    DISC_OUTPUT_FILE_NAME: ClassVar[str] = "output_data.pckl"

    class AuthenticationMethod(StrEnum):
        """The ssh authentication method."""

        PASSWORD = "password"
        PUBLIC_KEY = "public_key"

    discipline: MDODiscipline
    """The discipline to execute on the remote host."""

    local_workdir_path: Path
    """The path to the working directory."""

    _current_loc_id: str

    def __init__(
        self,
        discipline: MDODiscipline,
        local_workdir_path: str | Path,
        hostname: str,
        port: int = 22,
        username: str = "",
        password: str = "",
        ssh_public_key: str | Path = None,
        authentication_method: AuthenticationMethod = AuthenticationMethod.PASSWORD,
        remote_workdir_path: str | Path = None,
        pre_commands: Sequence[str] = (),
        transfer_inputs: Sequence[str] = (),
        transfer_outputs: Sequence[str] = (),
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
            ssh_public_key: The public key used for authentication on the remote host.
                Used when the authentication_method is
                SSHDisciplineWrapper.AuthenticationMethod.PUBLIC_KEY
            authentication_method: The method used for authentication on the remote host.
                Either public keys must be setup, or the plain password.
            remote_workdir_path: The path to the work directory on the remote host.
            pre_commands: The commands run on the remote host before deserialization and
                execution of the discipline on the remote host. This can be used to load
                the Python environment for instance.
            transfer_inputs: The sequence of files input data names that
                must be transferred before execution.
            transfer_outputs: The sequence of files output data names that
                must be transferred after execution.

        Raises:
            KeyError: if the transfer_inputs or transfer_outputs arguments are inconsistent
                with the discipline grammars.
        """  # noqa: D205, D212, D415
        super().__init__(discipline.name, grammar_type=discipline.grammar_type)
        self.discipline = discipline

        self.input_grammar = self.discipline.input_grammar
        self.output_grammar = self.discipline.output_grammar
        self.default_inputs = self.discipline.default_inputs
        self.local_workdir_path = Path(local_workdir_path)
        self.pickled_discipline = pickle.dumps(self.discipline)

        self.pre_commands = pre_commands

        self.__hostname = hostname
        self.__port = port
        self.__username = username
        self.__password = password
        self.__ssh_public_key_path = ssh_public_key
        self.__local_workdir_path = local_workdir_path
        self.__remote_workdir_path = remote_workdir_path
        self.__authentication_method = authentication_method
        self._check_authentication_method()

        if transfer_inputs is not None and not self.is_all_inputs_existing(
            transfer_inputs
        ):
            missing_in = set(transfer_inputs) - self.input_grammar
            raise KeyError(f"Invalid transfer_inputs: {missing_in}")
        if transfer_outputs is not None and not self.is_all_outputs_existing(
            transfer_outputs
        ):
            missing_out = set(transfer_outputs) - self.output_grammar
            raise KeyError(f"Invalid transfer_outputs: {missing_out}")
        self.__transfer_inputs = transfer_inputs
        self.__transfer_outputs = transfer_outputs

    def _check_authentication_method(self) -> None:
        """Check that the authentication method is correctly set.

        Raises:
            ValueError: If the authentication method is inconsistent
                with the given parameters.
        """
        if (
            self.__authentication_method == self.AuthenticationMethod.PASSWORD
            and not self.__password
        ):
            raise ValueError(
                "Password is not set while using password authentication for SSH connection."
            )
        elif (
            self.__authentication_method == self.AuthenticationMethod.PUBLIC_KEY
            and not self.__ssh_public_key_path
        ):
            raise ValueError(
                "SSH public key is not set while using public key authentication"
                " for SSH connection."
            )

    def _run_command(self, outputs_path: Path, current_workdir: Path) -> int:
        """Run the command on the remote node using SSH.

        Args:
            outputs_path: The path to the outputs serialized file.
            current_workdir: The path to the current work directory on the local host.

        Returns:
            The return code of the command run remotely.
        """
        ssh_session = self._open_ssh_session()

        start_time = time.time()
        LOGGER.debug(
            "Data written on local disk in %s seconds.", time.time() - start_time
        )

        discipline_path, input_path = self._write_inputs_to_disk(current_workdir)
        remote_workdir_path_root = str(self.__remote_workdir_path)
        remote_workdir_path = self.__current_remote_workdir_path.as_posix()
        discipline_path = discipline_path.as_posix()
        input_path = input_path.as_posix()

        ftp_client = self._open_sftp_client(ssh_session, remote_workdir_path_root)
        self._send_serialized_inputs(ftp_client, discipline_path, input_path)
        self._send_transfer_inputs(ftp_client)
        return_code, stdout, stderr = self._run_remote_command(
            ssh_session, remote_workdir_path
        )
        self._retrieve_serialized_outputs(ftp_client, current_workdir)
        self._handle_outputs(outputs_path, current_workdir)
        self._retrieve_transfer_outputs(ftp_client)

        ssh_session.close()

        LOGGER.debug("Job execution ended in %s", current_workdir)
        return return_code

    def _open_sftp_client(
        self, ssh_session: SSHClient, remote_workdir_path_root: Path
    ) -> SFTPClient:
        """Opens the SFTP client to allow file transfer.

        Args:
            ssh_session: The open SSH client
            remote_workdir_path_root: The root of the work directories on the remot host.

        Returns:
            The FTP client.
        """
        ftp_client = ssh_session.open_sftp()
        ftp_client.chdir(remote_workdir_path_root)
        ftp_client.mkdir(self._current_loc_id)
        ftp_client.chdir(self._current_loc_id)
        return ftp_client

    def _open_ssh_session(self) -> SSHClient:
        """Open a SSH session.

        Retuns:
            The SSH client.
        """
        try:
            ssh_client = SSHClient()
            ssh_client.set_missing_host_key_policy(AutoAddPolicy())
            if self.__authentication_method == self.AuthenticationMethod.PUBLIC_KEY:
                ssh_client.load_system_host_keys()
                ssh_client.connect(
                    self.__hostname,
                    self.__port,
                    self.__username,
                    key_filename=self.__ssh_public_key_path,
                    allow_agent=False,
                )
            elif self.__authentication_method == self.AuthenticationMethod.PASSWORD:
                ssh_client.connect(
                    self.__hostname,
                    self.__port,
                    self.__username,
                    self.__password,
                    allow_agent=False,
                )
        except AuthenticationException:
            raise AuthenticationException(
                "The authentication failed. Check your password or your ssh key."
            )

        return ssh_client

    def _send_serialized_inputs(
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
            remotepath=self.DISC_PICKLE_FILE_NAME,
            confirm=True,
        )
        ftp_client.put(
            localpath=str(input_path),
            remotepath=self.DISC_INPUT_FILE_NAME,
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
        if self.__transfer_inputs is None:
            return

        for data_name in self.__transfer_inputs:
            start_time = time.time()
            local_path = Path(self.local_data[data_name])
            if not local_path.exists():
                raise OSError(
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
        self, ftp_client: SFTPClient, current_workdir: Path
    ) -> None:
        """Retrieves the output data to the remote host after execution.

        Args:
            ftp_client: The FTP client.
            current_workdir: The path to the current work directory on the local host.
        """
        start_time = time.time()
        ftp_client.get(
            remotepath=str(self.DISC_OUTPUT_FILE_NAME),
            localpath=current_workdir / Path(self.DISC_OUTPUT_FILE_NAME),
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
        if self.__transfer_outputs is None:
            return

        for data_name in self.__transfer_outputs:
            start_time = time.time()
            file_name = Path(self.local_data[data_name]).name
            local_path = self.__local_workdir / file_name
            ftp_client.get(remotepath=file_name, localpath=str(local_path))
            LOGGER.debug(
                "Transfered input file %s to remote in %s seconds.",
                local_path,
                time.time() - start_time,
            )
            self.local_data[data_name] = str(local_path)

    def _run_remote_command(
        self, session: SSHClient, remote_workdir_path: Path
    ) -> tuple[int, str, str]:
        """Executes the gemseo-deserialize-run command on the remote host.

        Args:
            session: The SSH client.
            remote_workdir_path: The path to the work directory on the remote host.

        Returns:
            The return code of the command.
            The stdout of the command.
            The stderr of the command.
        """
        start_time = time.time()
        command_separator = "&&"
        cmd_change_dir = f"cd {remote_workdir_path} {command_separator} "
        cmd_run = (
            f"gemseo-deserialize-run {remote_workdir_path}"
            f" {self.DISC_PICKLE_FILE_NAME} {self.DISC_INPUT_FILE_NAME}"
            f" {self.DISC_OUTPUT_FILE_NAME}"
        )
        cmd = cmd_change_dir
        for command in self.pre_commands:
            cmd += f"{command} {command_separator} "
        cmd += cmd_run
        LOGGER.debug("Command = %s ", cmd)
        stdin, f_stdout, f_stderr = session.exec_command(cmd)
        return_code = f_stdout.channel.recv_exit_status()
        try:
            stdout = " ".join(f_stdout.readlines())
            stderr = " ".join(f_stderr.readlines())
        except Exception:
            stdout = "stdout not decoded"
            stderr = "stderr not decoded"
        if return_code != 0:
            raise RuntimeError(
                f"Remote execution failed.\n"
                f"Return code is {return_code}.\n"
                f"stdout is {stdout}.\n"
                f"stderr is {stderr}."
            )
        LOGGER.debug(
            "Remote discipline execution in %s seconds.", time.time() - start_time
        )
        return return_code, stdout, stderr

    def _handle_outputs(self, outputs_path: Path, current_workdir: Path) -> None:
        """Deserializes the output data and updates the discipline's local data.

        Args:
            outputs_path: The path to the serialized output data.
            current_workdir: The path to the current work directory on the local host.
        """
        if not outputs_path.exists():
            raise RuntimeError(
                "Serialized discipline outputs file does not exist {}.".format(
                    outputs_path
                )
            )
        with open(outputs_path, "rb") as output_file:
            output = pickle.load(output_file)
            if isinstance(output, tuple):
                error, trace = output
                LOGGER.error(
                    "Discipline %s execution failed in %s",
                    self.discipline.name,
                    current_workdir,
                )

                LOGGER.error(trace)
                raise error
            else:
                LOGGER.debug(
                    "Discipline %s execution succeded in %s",
                    self.discipline.name,
                    current_workdir,
                )
                self.local_data.update(output)

    def _create_current_workdir(self) -> Path:
        """Creates a unique local work directory.

        Returns:
            The path to the created work directory.
        """
        loc_id = str(uuid1()).split("-")[0]
        current_workdir = self.local_workdir_path / loc_id
        current_workdir.mkdir()
        self._current_loc_id = loc_id
        self.__current_remote_workdir_path = self.__remote_workdir_path / Path(
            self._current_loc_id
        )
        return current_workdir

    def _write_inputs_to_disk(self, current_workdir: Path) -> tuple[Path, Path]:
        """Serializes the input data to the disk for execution.

        Args:
            current_workdir: The path to the current work directory on the local host.

        Returns:
            The path to the serialized discipline, and the path to the serialized inputs.
        """
        discipline_path = current_workdir / self.DISC_PICKLE_FILE_NAME
        with open(discipline_path, "wb") as outf:
            outf.write(self.pickled_discipline)
        inputs_path = current_workdir / self.DISC_INPUT_FILE_NAME

        if self.__transfer_inputs:
            inputs_to_serialize = self.local_data.copy()
            for data_name in self.__transfer_inputs:
                local_path = Path(self.local_data[data_name])
                inputs_to_serialize[data_name] = str(
                    self.__current_remote_workdir_path / local_path.name
                )
        else:
            inputs_to_serialize = self.local_data

        serialized_local_data = pickle.dumps(inputs_to_serialize)
        with open(inputs_path, "wb") as outf:
            outf.write(serialized_local_data)
        return discipline_path, inputs_path

    def _run(self) -> None:
        current_workdir = self._create_current_workdir()

        outputs_path = current_workdir / self.DISC_OUTPUT_FILE_NAME

        self._write_inputs_to_disk(current_workdir)
        self._run_command(outputs_path, current_workdir)
