import subprocess
from pathlib import Path

from app.config import settings

def ensure_dir(p: Path) -> None:
    """ 确保 p 存在，若不存在则创建 """
    p.mkdir(parents=True, exist_ok=True)


def _run(cmd: list[str]) -> str:
    """
    运行 cmd，如果不成功则抛出异常

    :param cmd: 命令行程序
    """

    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\nSTDERR:\n{p.stderr[:2000]}")

    return p.stdout


def ffprobe_duration_ms(src: Path) -> int:
    """
    通过 ffprobe 获取 src(音/视频) 文件的时长，以 ms 返回

    :param src: 音/视频的文件路径
    :return: 时长（ms）
    """

    cmd = [
        settings.ffprobe_cmd,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(src),
    ]
    out = _run(cmd)
    if not out:
        return 0
    sec = float(out)
    return int(sec * 1000)


def transcode_to_wav_16k_mono(src: Path, dst: Path) -> None:
    """
    通过 ffmpeg 将 src(音/视频) 文件统一转码为 dst（WAV 文件： 16KHZ，单声道）

    :param src: 源音/视频文件路径
    :param dst: 转化后 WAV 音频文件路径
    :return: None
    """

    ensure_dir(dst.parent)
    cmd = [
        settings.ffmpeg_cmd,
        "-y",
        "-i", str(src),
        "-ac", str(settings.TARGET_CH),
        "-ar", str(settings.TARGET_SR),
        "-vn",
        "-f", "wav",
        str(dst),
    ]
    _run(cmd)