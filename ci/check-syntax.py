"""Check parent Python and shell syntax without executing the checked scripts."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', '.ansible', '__pycache__'}


def check_file(path):
    if path.suffix == '.py':
        # compile checks syntax and statement placement without importing or writing pyc.
        compile(path.read_bytes(), str(path), 'exec', dont_inherit=True)
    elif path.suffix == '.sh':
        subprocess.run(['bash', '-n', str(path)], check=True)


def main():
    checked = 0
    for directory in ('scripts', 'tests', 'support', 'ci'):
        root = ROOT / directory
        if not root.is_dir():
            raise RuntimeError(f'Missing syntax-check input: {directory}')
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.sh') and not SKIP.intersection(path.relative_to(ROOT).parts):
                check_file(path)
                checked += 1
    print(f'Syntax checked {checked} Python and shell files.')


if __name__ == '__main__':
    main()
