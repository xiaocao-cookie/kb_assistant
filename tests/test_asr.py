# test_asr.py
from pathlib import Path
from app.utils.asr import ASR


def test_asr():
    # 音频文件路径，请替换成你本地的 wav 文件
    wav_file = Path("../tests/output/study2.wav")
    if not wav_file.exists():
        print(f"音频文件不存在: {wav_file}")
        return

    # 初始化 ASR
    asr = ASR(model_name="base", device="cpu", compute_type="int8")

    # 转写音频
    segments, language = asr.transcribe(str(wav_file), language=None)

    # 输出识别结果
    print(f"识别语言: {language}")
    print("识别结果段落:")
    for seg in segments:
        print(f"[{seg.start_s:.2f}s - {seg.end_s:.2f}s]: {seg.text}")

if __name__ == "__main__":
    test_asr()
