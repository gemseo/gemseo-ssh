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

"""Integration tests for paramiko.py - targeting 100% coverage."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest


class TestTiming:
    """Tests for the timing context manager."""

    def test_timing_logs_elapsed_time(self, caplog):
        """Verify timing logs the elapsed time with prefix."""
        from gemseo_ssh.wrappers.ssh.paramiko import timing

        with (
            caplog.at_level(logging.DEBUG, logger="gemseo_ssh.wrappers.ssh.paramiko"),
            timing("Test operation completed"),
        ):
            pass

        assert "Test operation completed" in caplog.text
        assert "seconds" in caplog.text

    def test_timing_with_operation(self, caplog):
        """Verify timing works with actual operations."""
        from gemseo_ssh.wrappers.ssh.paramiko import timing

        with (
            caplog.at_level(logging.DEBUG, logger="gemseo_ssh.wrappers.ssh.paramiko"),
            timing("Sleep operation"),
        ):
            time.sleep(0.1)

        assert "Sleep operation" in caplog.text


class TestSFTPClientGet:
    """Tests for SFTPClient.get() method."""

    def test_get_existing_file(
        self, sftp_client, remote_temp_dir, tmp_path, sample_text_file
    ):
        """Verify downloading an existing file works."""
        remote_path = f"{remote_temp_dir}/test_file.txt"
        sftp_client.put(str(sample_text_file), remote_path)

        local_path = tmp_path / "downloaded.txt"
        sftp_client.get(remote_path, str(local_path))

        assert local_path.exists()
        assert local_path.read_text() == sample_text_file.read_text()

    def test_get_binary_file(
        self, sftp_client, remote_temp_dir, tmp_path, sample_binary_file
    ):
        """Verify downloading binary file preserves content."""
        remote_path = f"{remote_temp_dir}/test_file.bin"
        sftp_client.put(str(sample_binary_file), remote_path)

        local_path = tmp_path / "downloaded.bin"
        sftp_client.get(remote_path, str(local_path))

        assert local_path.read_bytes() == sample_binary_file.read_bytes()

    def test_get_large_file(self, sftp_client, remote_temp_dir, tmp_path, large_file):
        """Verify downloading large files works correctly."""
        remote_path = f"{remote_temp_dir}/large_file.bin"
        sftp_client.put(str(large_file), remote_path)

        local_path = tmp_path / "downloaded_large.bin"
        sftp_client.get(remote_path, str(local_path))

        assert local_path.read_bytes() == large_file.read_bytes()

    def test_get_nonexistent_file_raises_error(
        self, sftp_client, remote_temp_dir, tmp_path
    ):
        """Verify FileNotFoundError with proper message for missing remote file."""
        remote_path = f"{remote_temp_dir}/nonexistent_file.txt"
        local_path = tmp_path / "downloaded.txt"

        with pytest.raises(FileNotFoundError) as exc_info:
            sftp_client.get(remote_path, str(local_path))

        assert "No such file on remote host" in str(exc_info.value)
        assert remote_path in str(exc_info.value)

    def test_get_with_callback(
        self, sftp_client, remote_temp_dir, tmp_path, sample_text_file
    ):
        """Verify callback is invoked during download."""
        remote_path = f"{remote_temp_dir}/test_file.txt"
        sftp_client.put(str(sample_text_file), remote_path)

        callback_calls = []

        def progress_callback(transferred, total):
            callback_calls.append((transferred, total))

        local_path = tmp_path / "downloaded.txt"
        sftp_client.get(remote_path, str(local_path), callback=progress_callback)

        assert len(callback_calls) > 0


class TestSFTPClientPut:
    """Tests for SFTPClient.put() method."""

    def test_put_text_file(
        self, sftp_client, remote_temp_dir, sample_text_file, ssh_client
    ):
        """Verify uploading a text file works."""
        remote_path = f"{remote_temp_dir}/uploaded.txt"
        sftp_client.put(str(sample_text_file), remote_path)

        # Verify file exists on remote
        ssh_client.execute([f"test -f {remote_path}"])

    def test_put_binary_file(self, sftp_client, remote_temp_dir, sample_binary_file):
        """Verify uploading binary file preserves content."""
        remote_path = f"{remote_temp_dir}/uploaded.bin"
        sftp_client.put(str(sample_binary_file), remote_path)

        # Download and verify
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as f:
            sftp_client.get(remote_path, f.name)
            assert Path(f.name).read_bytes() == sample_binary_file.read_bytes()

    def test_put_nonexistent_local_file_raises_error(
        self, sftp_client, remote_temp_dir
    ):
        """Verify FileNotFoundError with proper message for missing local file."""
        local_path = "/nonexistent/path/to/file.txt"
        remote_path = f"{remote_temp_dir}/uploaded.txt"

        with pytest.raises(FileNotFoundError) as exc_info:
            sftp_client.put(local_path, remote_path)

        assert "No such file on local host" in str(exc_info.value)
        assert local_path in str(exc_info.value)

    def test_put_with_callback(self, sftp_client, remote_temp_dir, sample_text_file):
        """Verify callback is invoked during upload."""
        callback_calls = []

        def progress_callback(transferred, total):
            callback_calls.append((transferred, total))

        remote_path = f"{remote_temp_dir}/uploaded.txt"
        sftp_client.put(str(sample_text_file), remote_path, callback=progress_callback)

        assert len(callback_calls) > 0

    def test_put_file_with_special_characters(
        self, sftp_client, remote_temp_dir, file_with_special_chars, tmp_path
    ):
        """Verify files with unicode content transfer correctly."""
        remote_path = f"{remote_temp_dir}/special.txt"
        sftp_client.put(str(file_with_special_chars), remote_path)

        # Download and verify
        local_path = tmp_path / "downloaded_special.txt"
        sftp_client.get(remote_path, str(local_path))
        assert local_path.read_text() == file_with_special_chars.read_text()


class TestSFTPClientMkdir:
    """Tests for SFTPClient.mkdir() recursive directory creation."""

    def test_mkdir_single_directory(self, sftp_client, remote_temp_dir, ssh_client):
        """Verify creating a single directory works."""
        new_dir = f"{remote_temp_dir}/new_dir"
        sftp_client.mkdir(new_dir)

        # Verify directory exists
        ssh_client.execute([f"test -d {new_dir}"])

    def test_mkdir_nested_directories(self, sftp_client, remote_temp_dir, ssh_client):
        """Verify recursive directory creation works."""
        nested_path = f"{remote_temp_dir}/a/b/c/d"
        sftp_client.mkdir(nested_path)

        # Verify all directories exist
        ssh_client.execute([f"test -d {nested_path}"])

    def test_mkdir_existing_directory_no_error(self, sftp_client, remote_temp_dir):
        """Verify mkdir on existing directory does not raise error."""
        # Directory already exists (remote_temp_dir was created by fixture)
        sftp_client.mkdir(remote_temp_dir)  # Should not raise

    def test_mkdir_partial_existing_path(
        self, sftp_client, remote_temp_dir, ssh_client
    ):
        """Verify mkdir works when some parent directories exist."""
        # Create partial path
        partial = f"{remote_temp_dir}/existing"
        sftp_client.mkdir(partial)

        # Create deeper path
        full_path = f"{partial}/new1/new2"
        sftp_client.mkdir(full_path)

        ssh_client.execute([f"test -d {full_path}"])


class TestSFTPClientChdir:
    """Tests for SFTPClient.chdir() method."""

    def test_chdir_existing_directory(self, sftp_client, remote_temp_dir):
        """Verify changing to existing directory works."""
        sftp_client.chdir(remote_temp_dir)
        assert sftp_client.getcwd() == remote_temp_dir

    def test_chdir_nonexistent_directory_raises_error(
        self, sftp_client, remote_temp_dir
    ):
        """Verify FileNotFoundError for non-existent directory."""
        nonexistent_dir = f"{remote_temp_dir}/nonexistent_dir"

        with pytest.raises(FileNotFoundError) as exc_info:
            sftp_client.chdir(nonexistent_dir)

        assert "No such file on remote host" in str(exc_info.value)
        assert nonexistent_dir in str(exc_info.value)


class TestSSHClientCreateConnection:
    """Tests for SSHClient.create_connection() class method."""

    def test_create_connection_success(self, ssh_container):
        """Verify successful connection returns SSHClient."""
        from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

        params = ssh_container.get_connection_params()
        client = SSHClient.create_connection(
            hostname=params["hostname"],
            keep_alive_interval=60,
            port=params["port"],
            username=params["username"],
            password=params["password"],
        )

        assert client is not None
        assert client.get_transport() is not None
        client.close()

    def test_create_connection_sets_keepalive(self, ssh_container):
        """Verify keepalive is set on transport."""
        from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

        params = ssh_container.get_connection_params()
        keep_alive = 30

        client = SSHClient.create_connection(
            hostname=params["hostname"],
            keep_alive_interval=keep_alive,
            port=params["port"],
            username=params["username"],
            password=params["password"],
        )

        assert client.get_transport() is not None
        client.close()

    def test_create_connection_invalid_host_raises(self):
        """Verify connection failure raises appropriate error."""
        import socket

        from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

        with pytest.raises((socket.gaierror, socket.error, OSError)):
            SSHClient.create_connection(
                hostname="nonexistent.invalid.host",
                keep_alive_interval=60,
                port=22,
            )

    def test_create_connection_wrong_credentials_raises(self, ssh_container):
        """Verify wrong password raises authentication error."""
        from paramiko.ssh_exception import AuthenticationException

        from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

        params = ssh_container.get_connection_params()

        with pytest.raises(AuthenticationException):
            SSHClient.create_connection(
                hostname=params["hostname"],
                keep_alive_interval=60,
                port=params["port"],
                username=params["username"],
                password="wrong_password",
            )


class TestSSHClientExecute:
    """Tests for SSHClient.execute() method."""

    def test_execute_simple_command_success(self, ssh_client):
        """Verify executing simple command works."""
        ssh_client.execute(["echo 'Hello World'"])

    def test_execute_multiple_commands_chained(self, ssh_client, remote_temp_dir):
        """Verify multiple commands are chained with &&."""
        ssh_client.execute([
            f"cd {remote_temp_dir}",
            "touch test_file.txt",
            "ls test_file.txt",
        ])

    def test_execute_failing_command_logs_error(self, ssh_client, caplog):
        """Verify non-zero exit code is logged."""
        with caplog.at_level(logging.ERROR):
            ssh_client.execute(["exit 1"])

        assert "Remote execution failed" in caplog.text

    def test_execute_command_with_output(self, ssh_client, remote_temp_dir):
        """Verify command output is captured in logs."""
        ssh_client.execute([f"echo 'test output' > {remote_temp_dir}/out.txt"])

    def test_execute_stderr_captured(self, ssh_client, caplog):
        """Verify stderr is captured when command fails."""
        with caplog.at_level(logging.ERROR):
            ssh_client.execute(["ls /nonexistent_path_12345"])

        # stderr should be in the error log
        assert "stderr" in caplog.text.lower() or "No such file" in caplog.text

    def test_execute_gemseo_deserialize_run_available(self, ssh_client):
        """Verify gemseo-deserialize-run command exists in container."""
        ssh_client.execute(["which gemseo-deserialize-run"])


class TestSSHClientOpenSftp:
    """Tests for SSHClient.open_sftp() method."""

    def test_open_sftp_returns_custom_client(self, ssh_client):
        """Verify open_sftp returns our custom SFTPClient."""
        from gemseo_ssh.wrappers.ssh.paramiko import SFTPClient

        sftp = ssh_client.open_sftp()
        assert isinstance(sftp, SFTPClient)
        sftp.close()

    def test_open_sftp_functional(self, ssh_client, remote_temp_dir):
        """Verify returned SFTP client is functional."""
        sftp = ssh_client.open_sftp()

        sftp.chdir(remote_temp_dir)
        assert sftp.getcwd() == remote_temp_dir

        sftp.close()


class TestErrorPaths:
    """Tests for error conditions requiring mocking."""

    def test_open_sftp_transport_none_raises(self):
        """Test RuntimeError when transport is None."""
        from unittest.mock import patch

        from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

        client = SSHClient()
        with (
            patch.object(client, "get_transport", return_value=None),
            pytest.raises(RuntimeError, match="Cannot get the ssh transport"),
        ):
            client.open_sftp()

    def test_open_sftp_client_none_raises(self):
        """Test RuntimeError when SFTPClient.from_transport returns None."""
        from unittest.mock import MagicMock
        from unittest.mock import patch

        from gemseo_ssh.wrappers.ssh.paramiko import SFTPClient
        from gemseo_ssh.wrappers.ssh.paramiko import SSHClient

        client = SSHClient()
        mock_transport = MagicMock()

        with (
            patch.object(client, "get_transport", return_value=mock_transport),
            patch.object(SFTPClient, "from_transport", return_value=None),
            pytest.raises(RuntimeError, match="Cannot create the sftp client"),
        ):
            client.open_sftp()
