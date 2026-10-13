Pure-Python dependencies of the plugin go here – Theron adds this folder to the import path:

    pip install --target lib some-package

Libraries with native code (C extensions) don't work inside Theron. This README stays out of the package
(see `.theronignore`).
