"""运行全部测试（仅标准库，无需安装依赖）。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

suite = unittest.TestLoader().discover(str(ROOT / "tests"))
if suite.countTestCases() == 0:
    print("ERROR: no tests discovered under tests/ (fake green guard)", file=sys.stderr)
    sys.exit(1)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
