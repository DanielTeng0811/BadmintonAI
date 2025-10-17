"""
AI Client 初始化模組
AI client initialization for different API providers
"""
import openai


def initialize_client(api_mode: str, api_key: str):
    """
    根據模式和金鑰初始化 AI client

    Args:
        api_mode: API 模式 ("Gemini", "OpenAI 官方", "交大伺服器")
        api_key: API 金鑰

    Returns:
        openai.OpenAI: 初始化好的 OpenAI client

    Examples:
        >>> client = initialize_client("Gemini", "your_api_key")
        >>> client = initialize_client("OpenAI 官方", "your_api_key")
    """
    if api_mode == "Gemini":
        return openai.OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    elif api_mode == "交大伺服器":
        return openai.OpenAI(
            api_key=api_key,
            base_url="https://llm.nycu-adsl.cc"
        )
    else:  # OpenAI 官方
        return openai.OpenAI(api_key=api_key)
