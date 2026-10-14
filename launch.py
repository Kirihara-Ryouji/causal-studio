import multiprocessing
import os
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    # Libraries that print progress need a valid stream in a windowed executable.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from causal_studio.smoke import run
        raise SystemExit(run(sys.argv[2]))
    elif len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from causal_studio.selftest import run
        raise SystemExit(run(sys.argv[2]))
    else:
        from causal_studio.ui import main
        raise SystemExit(main())
