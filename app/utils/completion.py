import os
import httpx

from openai import OpenAI
from fastapi import HTTPException

from app.config import settings


def deepseek_chat_completion(*,
                             model: str = settings.model_name,
                             api_key: str = settings.openai_api_key,
                             temperature: float = 0.0,
                             messages: list[dict[str, str]],
                             timeout_s: float = 60.0,
                             stream: bool = False
                             ) -> str:
    """
    调用 LLM 进行自动补全，model 默认为 deepseek-chat

    :param model: 大语言模型，默认 deepseek-chat
    :param api_key: API KEY 用于身份认证, 默认为 deepseek 的API_KEY
    :param temperature: 温度, 默认 0.0
    :param messages: 模型对话的完整上下文
    :param timeout_s: 连接 OpenAI 超时的时间， 默认 60s
    :param stream: 是否流式输出，默认 False
    :return: LLM 生成的答案

    # model参数
    模型	        deepseek-chat	      deepseek-reasoner
    模型版本	  DeepSeek-V3.2-Exp       DeepSeek-V3.2-Exp
                  （非思考模式）             （思考模式）


    # temperature 参数默认为0.1
    场景	                        温度
    代码生成/数学解题             0.0
    数据抽取/分析	                1.0
    通用对话	                    1.3
    翻译	                        1.3
    创意类写作/诗歌创作	        1.5

    """
    url = "https://api.deepseek.com/"

    client = OpenAI(
        api_key=api_key,
        base_url=url,
        timeout=timeout_s,
    )

    # noinspection PyTypeChecker
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stream=stream
    )

    if stream:
        # 处理流式响应
        collected_chunks = []
        collected_messages = []

        for chunk in response:
            collected_chunks.append(chunk)
            chunk_message = chunk.choices[0].delta
            if chunk_message.content:
                collected_messages.append(chunk_message.content)
                print(chunk_message.content, end="", flush=True)

        # 拼接所有消息块
        full_content = ''.join(collected_messages)
        return full_content
    else:
        # 非流式响应
        content = response.choices[0].message.content
        return content


def openai_chat_complete(*,
                          model: str,
                          api_key: str,
                          messages: list[dict[str, str]],
                          timeout_s: float = 60.0
                          ) -> str:
    """
    调用 OpenAI Chat Completions API 生成模型回复。

    该函数使用 HTTP POST 请求直接调用 OpenAI 的 Chat Completion 接口，
    将给定的对话消息发送给模型，并返回生成的文本结果。

    :param model : 要使用的模型名称，例如 "gpt-3.5-turbo" 或 "gpt-4"。
    :param api_key : OpenAI API Key，用于身份验证。
    :param messages: 模型对话的完整上下文
    :param timeout_s: HTTP 请求超时时间（秒），默认为 60s
    :return 模型生成的回复
    """

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"OpenAI error: {r.status_code} {r.text[:300]}")
        data = r.json()
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        raise HTTPException(status_code=500, detail="OpenAI response parse error")