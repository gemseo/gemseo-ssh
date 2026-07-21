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
"""Specialized and improved paramiko ssh and sftp clients."""

from __future__ import annotations

from contextlib import contextmanager
from logging import getLogger
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING
from typing import Any

from paramiko import AutoAddPolicy
from paramiko.client import SSHClient as _SSHClient
from paramiko.common import o777
from paramiko.sftp_client import SFTPClient as _SFTPClient

if TYPE_CHECKING:
    from collections.abc import Iterator
    from collections.abc import Sequence

    from typing_extensions import Self

LOGGER = getLogger(__name__)


@contextmanager
def timing(logging_prefix: str) -> Iterator[None]:
    """A context manager to time code.

    Args:
        logging_prefix: The prefix for the logging message.
    """
    t1 = perf_counter()
    try:
        yield
    finally:
        LOGGER.debug("%s in %s seconds", logging_prefix, perf_counter() - t1)


class SFTPClient(_SFTPClient):
    """An improved SFTPClient.

    With timing info via logging and better error messages.
    """

    def get(self, remotepath, localpath, callback=None, prefetch=True) -> None:  # noqa: D102
        with timing(
            f"Transfered {remotepath} to {localpath} from remote to local host"
        ):
            try:
                super().get(remotepath, localpath, callback, prefetch)
            except FileNotFoundError:
                msg = f"No such file on remote host: {remotepath}"
                raise FileNotFoundError(msg) from None

    def put(self, localpath, remotepath, callback=None, confirm=True) -> None:  # noqa: D102
        with timing(
            f"Transfered {localpath} to {remotepath} from local to remote host"
        ):
            try:
                super().put(localpath, remotepath, callback, confirm)
            except FileNotFoundError:
                msg = f"No such file on local host: {localpath}"
                raise FileNotFoundError(msg) from None

    def mkdir(self, path, mode=o777) -> None:  # noqa: D102
        # Append a name that will not be used such that .parents
        # also deals with the last inner directory.
        path_ = Path(path) / "dummy"
        for parent_path in reversed(path_.parents):
            parent_path = parent_path.as_posix()
            try:
                self.stat(parent_path)
            except OSError:
                super().mkdir(parent_path, mode)

    def chdir(self, path=None) -> None:  # noqa: D102
        try:
            super().chdir(Path(path).as_posix())
        except FileNotFoundError:
            msg = f"No such file on remote host: {path}"
            raise FileNotFoundError(msg) from None


class SSHClient(_SSHClient):
    """Specialized ssh client."""

    @classmethod
    def create_connection(
        cls,
        hostname: str,
        keep_alive_interval: int,
        **connection_options: Any,
    ) -> Self:
        """Create a connected ssh client.

        Args:
            hostname: The hostname.
            keep_alive_interval: The time interval to keep the conenction alive.
            **connection_options: The ssh client connection options.

        Raises:
            RuntimeError: If the client transport is not existing.
        """
        client = cls()
        # Do not fail when connecting to a host for the first time.
        client.set_missing_host_key_policy(AutoAddPolicy())
        # Read the ~/.ssh/known_hosts.
        client.load_system_host_keys()
        client.connect(hostname, **connection_options)
        transport = client.get_transport()
        if transport is None:
            msg = "Cannot get the ssh transport"
            raise RuntimeError(msg)
        transport.set_keepalive(keep_alive_interval)
        return client

    def execute(self, cmd_lines: Sequence[str]) -> None:
        """Execute the command lines on the remote host.

        Args:
            cmd_lines: The command lines to execute.

        Raises:
            RuntimeError: If the execution failed.
        """
        LOGGER.debug("Command lines: \n%s", "\n".join(cmd_lines))

        cmd = " && ".join(cmd_lines)
        with timing("Remote discipline executed"):
            _, f_stdout, f_stderr = self.exec_command(cmd)

        try:
            stdout = " ".join(f_stdout.readlines())
            stderr = " ".join(f_stderr.readlines())
        except BaseException:  # noqa: BLE001
            stdout = "stdout not decoded"
            stderr = "stderr not decoded"

        return_code = f_stdout.channel.recv_exit_status()
        if return_code != 0:
            msg = (
                f"Remote execution failed.\n"
                f"Command lines: {cmd}\n"
                f"Return code is {return_code}.\n"
                f"stdout is {stdout}.\n"
                f"stderr is {stderr}."
            )
            LOGGER.error(msg)

    def open_sftp(self) -> SFTPClient:  # noqa: D102
        transport = self.get_transport()
        if transport is None:
            msg = "Cannot get the ssh transport"
            raise RuntimeError(msg)
        ftp_client = SFTPClient.from_transport(transport)
        if ftp_client is None:
            msg = "Cannot create the sftp client"
            raise RuntimeError(msg)
        return ftp_client
