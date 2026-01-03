from pathlib import Path
import subprocess

from app.config import settings

def ensure_dir(p: Path) -> None:
    """ 确保路径 p 存在，如不存在则创建 """
    p.mkdir(parents=True, exist_ok=True)


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
    将 src_path 对应的音频文件裁剪成 MP3 文件，并将其输出到 dst_path 路径下
    裁剪的区间为 [start_ms, end_ms]，输出 MP3 文件的采样率、声道数和码率分别为 sample_rate、channels 和 bitrate


    :param src_path: 原音频文件路径，需被 ffmpeg 识别
    :param dst_path: 目标 MP3 音频文件路径
    :param start_ms: 裁剪的开始时间（毫秒）
    :param end_ms: 裁剪的结束时间（毫秒）
    :param sample_rate: 输出的采样率
    :param channels: 输出的声道数
    :param bitrate: 输出的码率
    :return: 如果成功，则返回 None，否则引发异常
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

