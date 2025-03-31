import os
import sys
from pathlib import Path

if "tests" in Path(os.getcwd()).parts:
    sys.path.append(str(Path(os.getcwd(),'..').resolve()))
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
