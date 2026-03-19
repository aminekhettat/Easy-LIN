"""Easy-LIN application entry point.

By default this starts the Tk application. Pass ``--qt`` to run the
alternate PyQt application from the other integration branch.
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    use_qt = "--qt" in sys.argv

    if use_qt:
        from src.main_qt import run_qt_app

        run_qt_app(sys.argv)
        return

    try:
        import tkinter  # noqa: F401
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
