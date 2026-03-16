<!--
Copyright 2021 IRT Saint Exupéry, https://www.irt-saintexupery.com

This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
International License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->
# Configuration Reference

## `wrap_discipline_with_ssh` parameter reference

| Parameter | Type | Default | Description                                                                                                                          |
|---|---|---|--------------------------------------------------------------------------------------------------------------------------------------|
| `discipline` | `Discipline` | *required* | Any picklable GEMSEO `Discipline` and object inheriting from it: `MDA`, `MDOChain`, `MDOScenarioAdapter`, ...                        |
| `local_workdir_path` | `str | Path` | *required*                                                                                                                           | Local directory where UUID execution subdirectories are created. |
| `hostname` | `str` | *required* | SSH hostname or IP address of the remote machine.                                                                                    |
| `remote_workdir_path` | `str | Path` | `""`                                                                                                                                 | Remote base directory. If empty, uses the SSH default directory (usually `$HOME`). |
| `pre_commands` | `Iterable[str]` | `()` | Shell commands run on the remote host before discipline execution, chained with `&&`.                                                |
| `inputs_to_upload` | `Iterable[str]` | `()` | Names of discipline inputs whose values are local file paths to upload.                                                              |
| `outputs_to_download` | `Iterable[str]` | `()` | Names of discipline outputs whose values are remote file paths to download.                                                          |
| `copy_grammars` | `bool` | `False` | Copy original grammars (full validation) vs use `SimplerGrammar` (name-only validation).                                             |
| `**ssh_client_parameters` | | | Forwarded to [`paramiko.SSHClient.connect()`](https://docs.paramiko.org/en/latest/api/client.html#paramiko.client.SSHClient.connect). |

## SSH connection parameters

All keyword arguments beyond the ones listed above are forwarded directly to
paramiko's
[`SSHClient.connect()`](https://docs.paramiko.org/en/latest/api/client.html#paramiko.client.SSHClient.connect).
Common options include:

### Password authentication

```python
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="server.example.com",
    local_workdir_path="/tmp/workdir",
    username="jdoe",
    password="s3cret",
)
```

### Key-based authentication

```python
# Using a path to a private key file
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="server.example.com",
    local_workdir_path="/tmp/workdir",
    username="jdoe",
    key_filename="/home/jdoe/.ssh/id_rsa",
)
```

### Custom port

```python
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="server.example.com",
    local_workdir_path="/tmp/workdir",
    username="jdoe",
    port=2222,
    key_filename="/home/jdoe/.ssh/id_rsa",
)
```

### SSH agent / automatic key discovery

```python
# Let paramiko use the SSH agent or discover keys in ~/.ssh/
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="server.example.com",
    local_workdir_path="/tmp/workdir",
    username="jdoe",
    allow_agent=True,
    look_for_keys=True,
)
```

!!! tip "Using `~/.ssh/config`"

    You can also rely on your local `~/.ssh/config` file for host aliases, custom
    ports, ProxyJump, identity files, and other SSH options. Then simply pass the
    host alias as `hostname`:

    ```python
    # ~/.ssh/config entry:
    # Host myserver
    #     HostName 192.168.1.100
    #     User jdoe
    #     Port 2222
    #     IdentityFile ~/.ssh/id_rsa

    wrapper = wrap_discipline_with_ssh(
        discipline=disc,
        hostname="myserver",
        local_workdir_path="/tmp/workdir",
    )
    ```

## Pre-commands

The `pre_commands` parameter lets you run shell commands on the remote host before
the discipline is deserialized and executed. Commands are chained with `&&`, so if
any command fails, the execution stops.

### Virtualenv activation

```python
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="server.example.com",
    local_workdir_path="/tmp/workdir",
    pre_commands=(". /opt/venv/bin/activate",),
)
```

### PYTHONPATH for custom disciplines

```python
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="server.example.com",
    local_workdir_path="/tmp/workdir",
    pre_commands=("export PYTHONPATH=/path/to/my/modules:$PYTHONPATH",),
)
```

### Environment modules (HPC)

```python
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="hpc-login.example.com",
    local_workdir_path="/tmp/workdir",
    pre_commands=(
        "module load python/3.12",
        ". /opt/gemseo-env/bin/activate",
    ),
)
```

### Windows remote (PowerShell activation)

```python
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="windows-server.example.com",
    local_workdir_path="/tmp/workdir",
    pre_commands=(r"C:\envs\gemseo\Scripts\activate.bat",),
)
```

!!! note "Pre-commands on Windows SSH servers"

    Pre-commands are chained with `&&` (shell syntax). On a Windows SSH server
    running `cmd.exe`, `&&` works natively, but some commands may differ from their
    Unix equivalents. If the remote uses PowerShell, you may need to adapt the
    syntax (e.g., using `;` as a separator or calling `powershell -Command "..."`).

## Grammar handling

By default (`copy_grammars=False`), the SSH wrapper uses `SimplerGrammar`, which
only validates input/output **names** without checking types or shapes. This is
lightweight and works well in most cases.

Set `copy_grammars=True` to copy the original discipline's grammars, preserving
full type and shape validation:

```python
wrapper = wrap_discipline_with_ssh(
    discipline=disc,
    hostname="server.example.com",
    local_workdir_path="/tmp/workdir",
    copy_grammars=True,  # Full validation like the original discipline
)
```

## Remote requirements checklist

!!! info "Checklist for the remote machine"

    - **Same GEMSEO major version** as on the local machine (e.g., both at version 6).
    - **Remote GEMSEO environment activated** either using the `pre_commands` argument
      or by configuring the remote host to source the GEMSEO environment at
      the SSH session startup.
    - **All Python modules** imported by the discipline are installed on the
      remote.
    - **Write permissions** on the remote work directory (or `$HOME` if
      `remote_workdir_path` is empty).
    - **SSH port reachable** from the local machine (default: 22).

---

**Next:** [Working with File-Based Disciplines](file_transfers.md)
