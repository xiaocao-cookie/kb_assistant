from pathlib import Path
import subprocess

from app.config import settings

def ensure_dir(p: Path) -> None:
    """ 确保路径 p 存在，如不存在则创建 """
    p.mkdir(parents=True, exist_ok=True)

# todo: 写文档
def clip_audio_to_mp3(
        src_path: Path,
        dst_path: Path,
        start_ms: int,
        end_ms: int,
        sample_rate: int = 16_000,
        channels: int = 1,
        bitrate: str = "96k"
) -> None:
    """


    :param src_path:
    :param dst_path:
    :param start_ms:
    :param end_ms:
    :param sample_rate:
    :param channels:
    :param bitrate:
    :return:
    """

    ensure_dir(dst_path.parent)

    start_s = max(0.0, float(start_ms) / 1000.0)
    end_s = max(0.0, float(end_ms) / 1000.0)
    if end_s <= start_s:
        raise ValueError("开始时间不能大于结束时间")

    cmd = [
        settings.ffmpeg_cmd,
        "-y",
        "-ss", f"{start_s:.3f}",
        "-to", f"{end_s:.3f}",
        "-i", str(src_path),
        "-vn",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
        str(dst_path),
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

