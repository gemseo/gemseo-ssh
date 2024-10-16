<!--
Copyright 2021 IRT Saint Exupéry, https://www.irt-saintexupery.com

This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
International License. To view a copy of this license, visit
http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
Commons, PO Box 1866, Mountain View, CA 94042, USA.
-->

# gemseo-ssh

[![PyPI - License](https://img.shields.io/pypi/l/gemseo-ssh)](https://www.gnu.org/licenses/lgpl-3.0.en.html)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/gemseo-ssh)](https://pypi.org/project/gemseo-ssh/)
[![PyPI](https://img.shields.io/pypi/v/gemseo-ssh)](https://pypi.org/project/gemseo-ssh/)
[![Codecov branch](https://img.shields.io/codecov/c/gitlab/gemseo:dev/gemseo-ssh/develop)](https://app.codecov.io/gl/gemseo:dev/gemseo-ssh)

## Overview

SSH plugin for GEMSEO

## Installation

Install the latest version with `pip install gemseo-ssh`.

See [pip](https://pip.pypa.io/en/stable/getting-started/) for more information.

## Requirements

The same version of GEMSEO must be installed on the remote and local
machines, but not the GEMSEO-SSH plugin, which is only required on the
local machine.

## Usage

This GEMSEO SSH plugin allows to delegate the execution of a discipline
or any sub-process to a (such as an MDA or MDOScenario, or MDOChain) to
a remote machine via SSH.

It allows you to distribute MDO workflows across multiple machines and
multiple systems (Linux, Windows, MacOS).

It can be combined with GEMSEO\'s job scheduler interface to send
disciplines to a remote to a remote HPC and add them to the job
scheduler queue.
See the `gemseo.wrap_discipline_in_job_scheduler` method.

The SSH connection is handled with [paramiko](https://www.paramiko.org).
The settings for the SSH connections are passed as optional arguments
via the constructor of `SSHDisciplineWrapper` directly to `paramiko`'s SSH client.
Please refer to
[paramiko's `SSHClient` doc](https://docs.paramiko.org/en/latest/api/client.html#paramiko.client.SSHClient.connect)
for details on the
connection options.

## Examples

For example, we can submit a discipline to a remote host like this:

``` python
from gemseo import create_discipline
from gemseo_ssh import wrap_discipline_with_ssh
from numpy import array

analytic_disc = create_discipline("AnalyticDiscipline", expressions={"y":"2*x+1"})
remote_discipline = wrap_discipline_with_ssh(
    discipline=analytic_disc,
    hostname="remote_hostname",
    local_workdir_path= ".",
    remote_workdir_path="~/test_ssh",
    pkey="C:\\Users\\my_user_name\\.ssh\\id_rsa",
)
data = remote_discipline.execute({"x": array([1.0])})
```

A more complex process, like a MDA, can also be sent to a remote host:

``` python
from gemseo import create_discipline
from gemseo import create_mda
from gemseo_ssh import wrap_discipline_with_ssh

disciplines = create_discipline(["SobieskiPropulsion", "SobieskiAerodynamics",
                                 "SobieskiMission",  "SobieskiStructure"])
mda = create_mda("MDAChain", disciplines)
remote_discipline = wrap_discipline_with_ssh(
    discipline=mda,
    hostname="remote_hostname",
    local_workdir_path = ".",
    remote_workdir_path="~/test_ssh",
    username="my_username",
    password="my_password",
)

# Note that the default_inputs of the SSH discipline are the same
# as the default_inputs of the original discipline
couplings = remote_discipline.execute()
```

## Bugs and questions

Please use the [gitlab issue tracker](https://gitlab.com/gemseo/dev/gemseo-ssh/-/issues)
to submit bugs or questions.

## Contributing

See the [contributing section of GEMSEO](https://gemseo.readthedocs.io/en/stable/software/developing.html#dev).

## Contributors

- Jean-Christophe Giret
- François Gallard
- Nicolas Roussoully
- Antoine Dechaume
