"""
conftest.py - pytest設定
"""

import sys
from pathlib import Path

# プロジェクトルートとsrcディレクトリをパスに追加（パッケージインポート対応）
project_root = Path(__file__).parent.parent
src_dir = project_root / "src"

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
