from pathlib import Path

def ensure_dir(p: Path) -> None:
    """ 确保 p 存在，若不存在则创建 """
    p.mkdir(parents=True, exist_ok=True)