from dataclasses import dataclass


from app.utils.asr import ASRSegment

@dataclass
class Chunk:
    start_ms: int
    end_ms: int
    text: str


def merge_by_max_duration(
        segs: list[ASRSegment],
        max_ms: int = 25_000,
        min_ms: int = 6_000
) -> list[Chunk]:
    """
    将连续的 segs 分段合并成长度在 (min_ms, max_ms] 之间的块

    :param segs: ASRSegment 的列表，通过 ASR 转成的文本分割块
    :param max_ms: 最大毫秒数
    :param min_ms: 最小毫秒数
    :return: 长度在 (min_ms, max_ms] 之间的文本块
    """

    chunks: list[Chunk] = []
    cur_start = None
    cur_end = None
    buf: list[str] = []

    def flush():
        nonlocal cur_start, cur_end, buf
        if cur_start is None or cur_end is None:
            return
        text = " ".join(buf).strip()
        if text:
            chunks.append(Chunk(start_ms=cur_start, end_ms=cur_end, text=text))
        cur_start, cur_end, buf = None, None, []

    for s in segs:
        s_start = int(s.start_s * 1000)
        s_end = int(s.end_s * 1000)
        if cur_start is None:
            cur_start, cur_end = s_start, s_end
            buf = [s.text]
            continue

        new_end = max(cur_end, s_end)
        if (new_end - cur_start) <= max_ms:
            cur_end = new_end
            buf.append(s.text)
        else:
            if (cur_end - cur_start) < min_ms:
                cur_end = new_end
                buf.append(s.text)
            flush()
            cur_start, cur_end = s_start, s_end
            buf = [s.text]

    flush()
    return chunks