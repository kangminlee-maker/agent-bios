#!/usr/bin/env python3
"""Compatibility entrypoint for corpus_transaction.py; canonical implementation: instructions_transaction.py.

Retained for installed bridges, saved commands and third-party imports. Remove
only after the documented compatibility window and historical consumers close.
"""
from pathlib import Path
import importlib
import runpy
import sys

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name('instructions_transaction.py')), run_name="__main__")
else:
    _name = 'instructions_transaction'
    _module = importlib.import_module("." + _name, __package__) if __package__ else importlib.import_module(_name)
    for _symbol in tuple(vars(_module)):
        if "Instructions" in _symbol:
            setattr(_module, _symbol.replace("Instructions", "Corpus"), getattr(_module, _symbol))
    sys.modules[__name__] = _module
