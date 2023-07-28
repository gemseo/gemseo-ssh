..
    Copyright 2021 IRT Saint Exupéry, https://www.irt-saintexupery.com

    This work is licensed under the Creative Commons Attribution-ShareAlike 4.0
    International License. To view a copy of this license, visit
    http://creativecommons.org/licenses/by-sa/4.0/ or send a letter to Creative
    Commons, PO Box 1866, Mountain View, CA 94042, USA.

Usage
-----

This GEMSEO SSH plugin allows to delegate the execution of a discipline or any sub-process to a
(such as an MDA or MDOScenario, or MDOChain) to a remote machine via SSH.

It allows you to distribute MDO workflows across multiple machines and multiple
systems (Linux, Windows, MacOS).

It can be combined with GEMSEO's job scheduler interface to send disciplines to a remote
to a remote HPC and add them to the job scheduler queue.
See the gemseo.wrap_discipline_in_job_scheduler method.

Examples
--------

For example, we can submit a discipline to a remote host like this:

.. code-block:: python

    from gemseo import create_discipline
    from gemseo_ssh import wrap_discipline_with_ssh
    from numpy import array

    analytic_disc = create_discipline("AnalyticDiscipline", expressions={"y":"2*x+1"})
    remote_discipline = wrap_discipline_with_ssh(
        discipline=analytic_disc,
        hostname="remote_hostname",
         local_workdir_path= ".",
        remote_workdir_path="~/test_ssh",
        ssh_public_key="C:\\Users\\my_user_name\\.ssh\\id_rsa.pub",
        authentication_method="public_key"
    )
    data = remote_discipline.execute({"x": array([1.0])})

A more complex process, like a MDA, can also be sent to a remote host:

.. code-block:: python

    from gemseo import create_discipline
    from gemseo import create_mda
    from gemseo_ssh import wrap_discipline_with_ssh

    disciplines = create_discipline(["SobieskiPropulsion", "SobieskiAerodynamics",
                                     "SobieskiMission",  "SobieskiStructure"])
    mda = create_mda(
        "MDAChain",
        disciplines,
    )
    remote_discipline = wrap_discipline_with_ssh(
        discipline=mda,
        hostname="remote_hostname",
        local_workdir_path = ".",
        remote_workdir_path="~/test_ssh",
        username="my_username",
        password="my_password",
        authentication_method="password"
    )

    # Note that the default_inputs of the SSH discipline are the same
    # as the default_inputs of the original discipline
    couplings = remote_discipline.execute()


Requirements
------------
The same version of GEMSEO must be installed on the remote and local machines,
but not the GEMSEO-SSH plugin, which is only required on the local machine.

The SSH keys must be generated and exchanged in order to establish the SSH
connections without a password. See for example the ssh-copy-id utility.
Otherwise, the password and login must be written in clear text in the user script,
which is not good practice.

Bugs/Questions
--------------

Please use the gitlab issue tracker at
https://gitlab.com/gemseo/dev/gemseo-ssh/-/issues
to submit bugs or questions.

License
-------

The license is LGPL v3.

Contributors
------------

- Jean-Christophe Giret
- François Gallard
- Nicolas Roussoully
- Antoine Dechaume
