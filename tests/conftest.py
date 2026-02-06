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

"""Shared pytest fixtures for gemseo-ssh tests."""

from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from testcontainers.core.container import DockerContainer

if TYPE_CHECKING:
    from collections.abc import Generator

    from gemseo_ssh.wrappers.ssh.paramiko import SFTPClient
    from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

# Constants for SSH container
SSH_PASSWORD = "testpassword"
SSH_USER = "root"
SSH_PORT = 22


class SSHServerContainer(DockerContainer):
    """Custom SSH server container with gemseo installed."""

    def __init__(self, image: str = "gemseo-ssh-test:latest"):
        super().__init__(image)
        self.with_exposed_ports(SSH_PORT)

    def get_ssh_host(self) -> str:
        """Return the container host IP."""
        return self.get_container_host_ip()

    def get_ssh_port(self) -> int:
        """Return the mapped SSH port on the host."""
        return int(self.get_exposed_port(SSH_PORT))

    def get_connection_params(self) -> dict:
        """Return paramiko connection parameters."""
        return {
            "hostname": self.get_ssh_host(),
            "port": self.get_ssh_port(),
            "username": SSH_USER,
            "password": SSH_PASSWORD,
        }


def wait_for_ssh(
    host: str, port: int, timeout: int = 60, interval: float = 0.5
) -> None:
    """Wait for SSH port to be open.

    Args:
        host: The SSH host.
        port: The SSH port.
        timeout: Maximum time to wait in seconds.
        interval: Time between connection attempts in seconds.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection((host, port), timeout=interval):
                time.sleep(1.0)
                return
        except OSError:  # noqa: PERF203
            time.sleep(interval)
    msg = f"SSH server at {host}:{port} not ready after {timeout} seconds"
    raise TimeoutError(msg)


@pytest.fixture(scope="session")
def docker_image_built() -> str:
    """Build the Docker image once per session.

    Returns:
        The image tag name.
    """
    dockerfile_path = Path(__file__).parent / "docker" / "Dockerfile"
    # The build context is the tests directory, not the docker directory
    # because discipline.py is in tests/
    build_context = Path(__file__).parent.parent  # tests/
    image_tag = "gemseo-ssh-test:latest"

    subprocess.run(
        ["docker", "build", "-t", image_tag, "-f", str(dockerfile_path), "."],
        cwd=build_context,
        check=True,
        capture_output=True,
    )
    return image_tag


@pytest.fixture(scope="session")
def ssh_container(docker_image_built) -> Generator[SSHServerContainer, None, None]:
    """Session-scoped SSH server container.

    Starts once per test session and is reused across all integration tests.
    """
    container = SSHServerContainer(image=docker_image_built)
    with container:
        # Wait for SSH to be ready by checking if the port is open
        ssh_host = container.get_ssh_host()
        ssh_port = container.get_ssh_port()
        wait_for_ssh(ssh_host, ssh_port, timeout=60)
        yield container


@pytest.fixture
def ssh_client(ssh_container) -> Generator[SSHClient, None, None]:
    """Function-scoped SSH client connected to the test container.

    Creates a fresh connection for each test function.
    """
    from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

    params = ssh_container.get_connection_params()
    client = SSHClient.create_connection(
        hostname=params["hostname"],
        keep_alive_interval=60,
        port=params["port"],
        username=params["username"],
        password=params["password"],
    )
    yield client
    client.close()


@pytest.fixture
def sftp_client(ssh_client) -> Generator[SFTPClient, None, None]:
    """Function-scoped SFTP client.

    Opens an SFTP session on the existing SSH connection.
    """
    sftp = ssh_client.open_sftp()
    yield sftp
    sftp.close()


@pytest.fixture
def local_temp_dir(tmp_path) -> Path:
    """Provide a temporary local directory for test files."""
    return tmp_path


@pytest.fixture
def remote_temp_dir(ssh_client, sftp_client) -> Generator[str, None, None]:
    """Create a temporary directory on the remote server.

    Cleans up after the test.
    """
    remote_dir = f"/tmp/test_{uuid.uuid4().hex}"
    sftp_client.mkdir(remote_dir)
    yield remote_dir
    # Cleanup: remove directory recursively
    ssh_client.execute([f"rm -rf {remote_dir}"])


@pytest.fixture
def sample_text_file(local_temp_dir) -> Path:
    """Create a sample text file for upload tests."""
    file_path = local_temp_dir / "sample.txt"
    file_path.write_text("Hello, SSH!")
    return file_path


@pytest.fixture
def sample_binary_file(local_temp_dir) -> Path:
    """Create a sample binary file for upload tests."""
    file_path = local_temp_dir / "sample.bin"
    file_path.write_bytes(bytes(range(256)))
    return file_path


@pytest.fixture
def large_file(local_temp_dir) -> Path:
    """Create a large file (1MB) for transfer performance tests."""
    file_path = local_temp_dir / "large_file.bin"
    file_path.write_bytes(os.urandom(1024 * 1024))
    return file_path


@pytest.fixture
def file_with_special_chars(local_temp_dir) -> Path:
    """Create a file with special characters in content."""
    file_path = local_temp_dir / "special_chars.txt"
    file_path.write_text("Unicode: \u4e2d\u6587 \u00e9\u00e8\u00ea \u2603")
    return file_path
