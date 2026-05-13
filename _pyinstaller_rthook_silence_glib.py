"""PyInstaller runtime hook: silence GLib-GIO startup warnings on Windows.

PyInstaller runs every file listed in a spec's `runtime_hooks=` argument
during the bootstrap phase, BEFORE control passes to the main script. That
makes it the right place to set env vars that need to be honoured by
later-loaded C libraries -- in our case, GLib's GIO subsystem, which
otherwise spams stderr with "supports N extensions but has no verbs"
warnings for every UWP app on the machine.

Doing the same thing at the top of __main__.py is not enough: by the time
the Python interpreter starts executing user code, PyInstaller's bootloader
has already resolved and loaded the bundled DLLs (libglib, libgio,
libgobject), and any one-time initialization those libraries do at load
time has already happened.
"""
import os as _os

_os.environ.setdefault("GIO_USE_VFS", "local")
_os.environ.setdefault("G_MESSAGES_DEBUG", "")
