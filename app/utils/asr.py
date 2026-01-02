from dataclasses import dataclass
from typing import Optional, List

from faster_whisper import WhisperModel


@dataclass
class ASRSegment:
    start_s: float
    end_s: float
    text: str


class ASR:
    """ Automatic Speech Recognized, 自动语音识别，即音频转文字 """

    def __init__(self,
                 model_name: str = "base",
                 device: str = "cpu",
                 compute_type: str = "int8"
                 ):
        """
        初始化 ASR

        :param model_name: 模型名称，用于加载预训练好的模型权重 默认 "base"
        :param device: 模型用于计算的设备, 默认 "cpu"
        :param compute_type: 量化的程度，默认 "int8"
        """

        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

    def transcribe(self, wav_path: str, language: Optional[str] = None) -> tuple[list[ASRSegment], Optional[str]]:
        """
        将 wav_path 对应的音频按照 language 解析，生成文本段和语言信息

        :param wav_path: 输入的音频文件路径
        :param language: 指定使用什么语言去识别 wave_path
        :return: 一个元组（ASRSegment 的列表，对应的语言）
        """

        segments_iter, info = self.model.transcribe(
            wav_path,
            language=language,
            vad_filter=False                        # 不过滤静音段，vad —— Voice Activity Detection
        )

        segs: List[ASRSegment] = []
        for s in segments_iter:
            txt = (s.text or "").strip()
            if not txt:
                continue
            segs.append(ASRSegment(start_s=float(s.start), end_s=float(s.end), text=txt))
        lang = getattr(info, "language", None)
        return segs, lang
