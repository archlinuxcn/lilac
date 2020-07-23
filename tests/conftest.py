import pathlib
import sys

# sys.path does not support `Path`s yet
this_dir = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(this_dir.parents[1]))
sys.path.insert(0, str(this_dir.parents[1] / 'lilac2' / 'vendor'))
