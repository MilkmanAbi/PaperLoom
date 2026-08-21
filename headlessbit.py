#!/usr/bin/env python3
"""
Entry point for HeadlessBit - PaperLoom's functions over a plain-text shell,
no display required. See paperloom/headlessbit.py for the full picture.

    python headlessbit.py                          interactive shell
    python headlessbit.py components button         one-shot command
    echo "new pyside6" | python headlessbit.py       scripted (e.g. by an AI agent)
"""
from paperloom.headlessbit import main

if __name__ == "__main__":
    main()
