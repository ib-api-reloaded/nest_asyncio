anest-asyncio
=============

|Build| |Status| |PyPiVersion| |License| |Downloads|

``anest-asyncio`` is the maintained continuation of ``nest_asyncio``,
published under a new name by the ib-api-reloaded project alongside
``aeventkit`` and ``ib_async``. It keeps the original import name and
public API, so existing code keeps working unchanged:

.. code-block:: python

    import nest_asyncio
    nest_asyncio.apply()

It adds support for current Python releases (3.11 through 3.14),
including Python 3.14's task and event-loop changes.

Install either ``anest-asyncio`` or the original ``nest_asyncio``, not
both: they provide the same ``nest_asyncio`` module.

Introduction
------------

By design asyncio `does not allow <https://github.com/python/cpython/issues/66435>`_
its event loop to be nested. This presents a practical problem:
When in an environment where the event loop is
already running it's impossible to run tasks and wait
for the result. Trying to do so will give the error
"``RuntimeError: This event loop is already running``".

The issue pops up in various environments, such as web servers,
GUI applications and in Jupyter notebooks.

This module patches asyncio to allow nested use of ``asyncio.run`` and
``loop.run_until_complete``.

Recent compatibility work in this repository adapts ideas first explored in
`Chaoses-Ib/nest-asyncio2 <https://github.com/Chaoses-Ib/nest-asyncio2>`_,
then rewrites them for the ``nest_asyncio`` codebase and packaging model.
The first imported idea is Python 3.12+ support for
``asyncio.run(..., loop_factory=...)``.
The second is Python 3.14 mixed-task handling when ``apply()`` runs inside an
already-active task.
The third is draining ``call_soon`` callbacks scheduled during nested task
completion before ``run_until_complete()`` returns.

Installation
------------

.. code-block::

    pip install anest-asyncio

Python 3.11 or higher is required.

Usage
-----

.. code-block:: python

    import nest_asyncio
    nest_asyncio.apply()

Optionally the specific loop that needs patching can be given
as argument to ``apply``, otherwise the current event loop is used.
An event loop can be patched whether it is already running
or not. Only event loops from asyncio can be patched;
Loops from other projects, such as uvloop or quamash,
generally can't be patched.

Development
-----------

This project is tested on CPython 3.11, 3.12, 3.13, 3.14, and PyPy 3.11.

Using ``uv``:

.. code-block:: bash

    uv sync --group dev
    make test         # default interpreter
    make test-matrix  # 3.11 - 3.14, one isolated environment each
    make lint         # ruff + mypy

Using ``poetry``:

.. code-block:: bash

    poetry install --with dev
    poetry run python -m unittest tests.nest_test

Acknowledgements
----------------

Some recent compatibility fixes and regression tests were adapted from
``Chaoses-Ib/nest-asyncio2`` after review and then integrated back into this
core project. The code here intentionally keeps the original ``nest_asyncio``
public interface while incorporating the useful runtime fixes discovered in
that fork.

.. |Build| image:: https://github.com/ib-api-reloaded/nest_asyncio/actions/workflows/test.yml/badge.svg
   :alt: Build
   :target: https://github.com/ib-api-reloaded/nest_asyncio/actions

.. |PyPiVersion| image:: https://img.shields.io/pypi/v/anest-asyncio.svg
   :alt: PyPi
   :target: https://pypi.org/project/anest-asyncio/

.. |Status| image:: https://img.shields.io/badge/status-stable-green.svg
   :alt:

.. |License| image:: https://img.shields.io/badge/license-BSD-blue.svg
   :alt:

.. |Downloads| image:: https://static.pepy.tech/badge/anest-asyncio/month
   :alt: Number of downloads
   :target: https://pepy.tech/project/anest-asyncio
