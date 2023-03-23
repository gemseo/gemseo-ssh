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
"""Job schedulers interface."""
from __future__ import annotations

import pickle
import time
from enum import Enum
from logging import getLogger
from pathlib import Path
from uuid import uuid1
import numpy as np

import paramiko
from gemseo.core.discipline import MDODiscipline
from paramiko.ssh_exception import AuthenticationException

LOGGER = getLogger(__name__)


class SSHDisciplineWrapper(MDODiscipline):
    """A discipline that delegate the computation to a distant node through SSH."""

    DISC_PICKLE_FILE_NAME = "discipline.pckl"
    DISC_INPUT_FILE_NAME = "input_data.pckl"
    DISC_OUTPUT_FILE_NAME = "output_data.pckl"
    AUTHENTIFICATION_METHOD = Enum(
        "AUTHENTIFICATION_METHOD", ["password", "public_key"]
    )

    discipline: MDODiscipline
    """The discipline to wrapp in the job scheduler."""
    workdir_path: Path
    """The path to the workdir."""
    _current_loc_id: str

    def __init__(
        self,
        discipline: MDODiscipline,
        workdir_path: Path,
        hostname: str,
        port: int = 22,
        username: str = None,
        password: str = None,
        ssh_public_key=None,
        authentification_method=AUTHENTIFICATION_METHOD.password,
        distant_workdir=None,
        pre_commands=None,
        transfer_inputs=None,
        transfer_outputs=None,
    ):
        """Constructor.

        Args:
            discipline: The discipline to wrapp in the job scheduler.
            workdir_path: The path to the workdir.

        Raises:
            OSError if job_template_path does not exist.
            KeyError: if some data names in transfer_inputs or transfer_outputs are not
                in the grammars.
        """
        super().__init__(discipline.name, grammar_type=discipline.grammar_type)
        self.discipline = discipline

        self.input_grammar = self.discipline.input_grammar
        self.output_grammar = self.discipline.output_grammar
        self.default_inputs = self.discipline.default_inputs
        self.workdir_path = Path(workdir_path)
        self.pickled_discipline = pickle.dumps(self.discipline)

        self.pre_commands = pre_commands if pre_commands else []

        self.__hostname = hostname
        self.__port = port
        self.__username = username
        self.__password = password
        self.__ssh_public_key_path = ssh_public_key
        self.__local_workdir = workdir_path
        self.__distant_workdir = distant_workdir
        self.__authentification_method = authentification_method

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

        self._check_authentification_method()

    def _check_authentification_method(self):
        """Check that the authentification method is correctly set.

        Raises:
            ValueError: If the authentification method is inconsistent
             with the given parameters.
        """
        if (
            self.__authentification_method == self.AUTHENTIFICATION_METHOD.password
            and not self.__password
        ):
            raise ValueError(
                "Password is not set while using password authentification for SSH connection."
            )
        elif (
            self.__authentification_method == self.AUTHENTIFICATION_METHOD.public_key
            and not self.__ssh_public_key_path
        ):
            raise ValueError(
                "SSH public key is not set while using public key authentification"
                " for SSH connection."
            )

    def _run_command(self, outputs_path, current_workdir):
        """Run the command on the distant node using SSH.

        Args:
            current_workdir: The current workdir path.

        Returns:
            The return code of the command run distantly.
        """
        s = self._open_ssh_session()

        timer = time.time()
        LOGGER.debug("Data written on local disk in %s seconds.", time.time() - timer)

        discipline_path, input_path = self._write_inputs_to_disk(current_workdir)
        distant_workdir_root = str(self.__distant_workdir)
        distant_workdir = self.__current_distant_workdir.as_posix()
        discipline_path = discipline_path.as_posix()
        input_path = input_path.as_posix()

        ftp_client = self._open_sftp_client(s, distant_workdir_root)
        self._send_serialized_inputs(ftp_client, discipline_path, input_path)
        self._send_transfer_inputs(ftp_client)
        return_code, stdout, stderr = self._run_distant_command(s, distant_workdir)
        self._retrieve_serialized_outputs(ftp_client, current_workdir)
        self._handle_outputs(outputs_path, current_workdir)
        self._retrieve_transfer_outputs(ftp_client, current_workdir)

        s.close()

        LOGGER.debug("Job execution ended in %s", current_workdir)
        return return_code

    def _open_sftp_client(self, s, distant_workdir_root):
        ftp_client = s.open_sftp()
        ftp_client.chdir(distant_workdir_root)
        ftp_client.mkdir(self._current_loc_id)
        ftp_client.chdir(self._current_loc_id)
        return ftp_client

    def _open_ssh_session(self):
        """Open a SSH session."""
        try:
            s = paramiko.SSHClient()
            s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            if (
                self.__authentification_method
                == self.AUTHENTIFICATION_METHOD.public_key
            ):
                s.load_system_host_keys()
                s.connect(
                    self.__hostname,
                    self.__port,
                    self.__username,
                    key_filename=self.__ssh_public_key_path,
                    allow_agent=False
                )
            elif (
                self.__authentification_method == self.AUTHENTIFICATION_METHOD.password
            ):
                s.connect(
                    self.__hostname, self.__port, self.__username, self.__password, allow_agent=False
                )
        except AuthenticationException:
            raise AuthenticationException(
                "The authentification failed. Check your password or your ssh key."
            )

        return s

    def _send_serialized_inputs(self, ftp_client, discipline_path, input_path):
        timer = time.time()
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
            "Input data written on distant node in %s seconds.", time.time() - timer
        )

    def _send_transfer_inputs(self, ftp_client):
        if self.__transfer_inputs is None:
            return

        for data_name in self.__transfer_inputs:
            timer = time.time()
            local_path = Path(self.local_data[data_name][0])
            if not local_path.exists():
                raise OSError(
                    f"Input to transfer {data_name} is not a file or does not exist!"
                )
            ftp_client.put(
                localpath=str(local_path),
                remotepath=str(Path(self.__current_distant_workdir) / local_path.name),
                confirm=True,
            )
            LOGGER.debug(
                "Transfer data written on distant node in %s seconds.",
                time.time() - timer,
            )

    def _retrieve_serialized_outputs(self, ftp_client, current_workdir):
        timer = time.time()
        local_output_path = current_workdir / Path(self.DISC_OUTPUT_FILE_NAME)
        ftp_client.get(
            remotepath=str(self.DISC_OUTPUT_FILE_NAME), localpath=local_output_path
        )
        LOGGER.debug(
            "Copy of distant data to local node in %s seconds.", time.time() - timer
        )

    def _retrieve_transfer_outputs(self, ftp_client, current_workdir):
        if self.__transfer_outputs is None:
            return

        for data_name in self.__transfer_outputs:
            timer = time.time()
            remotepath = Path(self.local_data[data_name])
            local_output_path = self.__local_workdir / remotepath.name
            ftp_client.get(remotepath=str(remotepath), localpath=str(local_output_path))
            LOGGER.debug(
                "Transfer outputs to local node in %s seconds.", time.time() - timer
            )
            self.local_data[data_name] = str(local_output_path)

    def _run_distant_command(self, session, distant_workdir):
        timer = time.time()
        command_separator = "&&"
        cmd_change_dir = f"cd {distant_workdir} {command_separator} "
        cmd_run = (
            f"gemseo-deserialize-run {distant_workdir}"
            f" {self.DISC_PICKLE_FILE_NAME} {self.DISC_INPUT_FILE_NAME}"
            f" {self.DISC_OUTPUT_FILE_NAME}"
        )
        cmd = cmd_change_dir
        for command in self.pre_commands:
            cmd += f"{command} {command_separator} "
        cmd += cmd_run
        LOGGER.debug(f"Command = {cmd}")
        stdin, f_stdout, f_stderr = session.exec_command(cmd)
        return_code = f_stdout.channel.recv_exit_status()
        try:
            stdout = " ".join(f_stdout.readlines())
            stderr = " ".join(f_stderr.readlines())
        except:
            stdout = "stdout not decoded"
            stderr = "stderr not decoded"
        if return_code != 0:
            raise RuntimeError(
                f"Remote execution failed.\n"
                f"Return code is {return_code}.\n"
                f"stdout is {stdout}.\n"
                f"stderr is {stderr}."
            )
        LOGGER.debug("Remote discipline execution in %s seconds.", time.time() - timer)
        return return_code, stdout, stderr

    def _handle_outputs(self, outputs_path, current_workdir):
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

    def _create_current_workdir(self):
        loc_id = str(uuid1()).split("-")[0]
        current_workdir = self.workdir_path / loc_id
        current_workdir.mkdir()
        self._current_loc_id = loc_id
        self.__current_distant_workdir = self.__distant_workdir / Path(
            self._current_loc_id
        )
        return current_workdir

    def _write_inputs_to_disk(self, current_workdir):
        discipline_path = current_workdir / self.DISC_PICKLE_FILE_NAME
        with open(discipline_path, "wb") as outf:
            outf.write(self.pickled_discipline)
        inputs_path = current_workdir / self.DISC_INPUT_FILE_NAME

        if self.__transfer_inputs:
            inputs_to_serialize = self.local_data.copy()
            for data_name in self.__transfer_inputs:
                local_path = Path(self.local_data[data_name][0])
                inputs_to_serialize[data_name] = np.array([str(
                    self.__current_distant_workdir / local_path.name
                )])
        else:
            inputs_to_serialize = self.local_data

        serialized_local_data = pickle.dumps(inputs_to_serialize)
        with open(inputs_path, "wb") as outf:
            outf.write(serialized_local_data)
        return discipline_path, inputs_path

    def _run(self):
        current_workdir = self._create_current_workdir()

        outputs_path = current_workdir / self.DISC_OUTPUT_FILE_NAME

        discipline_path, inputs_path = self._write_inputs_to_disk(current_workdir)
        self._send_data_to_distant_node(discipline_path, inputs_path)
        self._run_command(outputs_path, current_workdir)
        self._retrieved_data_from_distant_node(current_workdir)

    def _send_data_to_distant_node(self, discipline_path, inputs_path):
        pass

    def _retrieved_data_from_distant_node(self, current_workdir):
        pass
