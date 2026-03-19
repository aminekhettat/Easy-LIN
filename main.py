"""Application entry point for Easy-LIN.

:mod:`main` starts the Tk interface by default and can launch the preserved
PyQt interface with the ``--qt`` switch.

:author: Amine Khettat
:company: BLIND SYSTEMS
:website: https://www.blindsystems.org
:version: 0.5.0
:copyright: Copyright (c) 2026 Amine Khettat
:license: Easy-LIN Source-Available License Version 1.0. See LICENSE.
:disclaimer: Provided "AS IS", without warranties or liability, as described
    in LICENSE.
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    """Launch the requested Easy-LIN user interface."""
    use_qt = "--qt" in sys.argv

    if use_qt:
        from src.main_qt import run_qt_app

        run_qt_app(sys.argv)
        return

    try:
        import tkinter

        getattr(tkinter, "TkVersion", None)
    except ImportError:
        print(
            "ERROR: tkinter is not available.\n"
            "Install tkinter or run the PyQt variant with: python main.py --qt",
            file=sys.stderr,
        )
        sys.exit(1)

    from src.gui.main_window import MainWindow

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
