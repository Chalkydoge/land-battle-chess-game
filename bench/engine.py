"""Load a snapshot's algorithms.py as an isolated module."""

import sys
import importlib.util
from pathlib import Path


def load(tag, snapshot_dir):
    """Load <snapshot_dir>/algorithms.py as module 'bench_engine_<tag>'.

    The snapshot dir is prepended to sys.path during loading so that
    `from pieceClasses import *` inside algorithms.py resolves to the
    snapshot's own pieceClasses.py.
    """
    snapshot_dir = Path(snapshot_dir)
    algo_path = snapshot_dir / "algorithms.py"
    if not algo_path.is_file():
        raise FileNotFoundError(f"missing algorithms.py in snapshot {snapshot_dir}")

    mod_name = f"bench_engine_{tag}"
    spec = importlib.util.spec_from_file_location(mod_name, algo_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot build import spec for {algo_path}")
    module = importlib.util.module_from_spec(spec)

    sys.path.insert(0, str(snapshot_dir))
    try:
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(str(snapshot_dir))
        except ValueError:
            pass
    return module
