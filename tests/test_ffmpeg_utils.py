from pathlib import Path
from app.ingestion.audio_loader import ffprobe_duration_ms, transcode_to_wav_16k_mono  # 替换成你的模块名


def main():
    # 输入音频文件路径（替换成你本地的测试文件）
    src_file = Path("./study7.mp3")

    if not src_file.exists():
        print(f"音频文件不存在：{src_file}")
        return

    # 获取原音频时长
    duration_ms = ffprobe_duration_ms(src_file)
    print(f"原音频时长: {duration_ms} ms")

    # 转码输出路径
    dst_file = Path("output/study7.wav")

    # 转码为 16k 单声道 WAV
    transcode_to_wav_16k_mono(src_file, dst_file)
    print(f"转码完成: {dst_file}")

    # 获取转码后的时长
    duration_ms_out = ffprobe_duration_ms(dst_file)
    print(f"转码后音频时长: {duration_ms_out} ms")


if __name__ == "__main__":
    main()
