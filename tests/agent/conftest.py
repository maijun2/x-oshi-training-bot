"""agent/ 配下はパッケージではなくデプロイパッケージのルート直下に置かれるため sys.path に足す"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[2] / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
