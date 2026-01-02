import subprocess
from pathlib import Path


def ensure_dir(p: Path) -> None:
    """ 确保 p 存在，若不存在则创建 """
    p.mkdir(parents=True, exist_ok=True)


def ffprobe_duration_ms(src: Path) -> int:
    """
    通过 ffprobe 获取 src(音/视频) 文件的时长，以 ms 返回

    :param src: 音/视频的文件路径
    :return: 时长（ms）
    """

    cmd = [
        "/home/supercao/Downloads/ffmpeg-master-latest-linux64-gpl/bin/ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(src),
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8").strip()
    if not out:
        return 0
    sec = float(out)
    return int(sec * 1000)


def transcode_to_wav_16k_mono(src: Path, dst: Path) -> None:
    """
    将 src(音/视频) 文件统一转码为 dst（WAV 文件： 16KHZ，单声道）

    :param src: 源音/视频文件路径
    :param dst: 转化后 WAV 音频文件路径
    :return: None
    """

    ensure_dir(dst.parent)
    cmd = [
        "/home/supercao//Downloads/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg",
        "-y",
        "-i", str(src),
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        str(dst),
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)