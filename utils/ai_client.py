"""
AI Client 初始化模組
AI client initialization for different API providers

支援 OpenAI、Gemini、交大伺服器、Claude (Anthropic)
Claude 模式透過 Adapter Pattern 將 Anthropic SDK 包裝為 OpenAI 相容介面，
讓所有呼叫端 (analysis_workflow, front_page, LLM_as_a_Judge)
無需任何改動即可使用 Claude。
"""
import openai


# ---------------------------------------------------------------------------
# Anthropic → OpenAI 介面適配器 (Adapter Pattern)
# ---------------------------------------------------------------------------
# 目的：讓所有呼叫端的 `client.chat.completions.create(model, messages, **kwargs)`
# 以及 `response.choices[0].message.content` / `response.usage.total_tokens`
# 在 Claude 模式下也能正常運作，不需改動任何呼叫端程式碼。
# ---------------------------------------------------------------------------

class _AnthropicUsage:
    """模擬 OpenAI response.usage 物件"""
    def __init__(self, input_tokens: int, output_tokens: int):
        self.prompt_tokens = input_tokens
        self.completion_tokens = output_tokens
        self.total_tokens = input_tokens + output_tokens


class _AnthropicMessage:
    """模擬 OpenAI response.choices[0].message 物件"""
    def __init__(self, content: str):
        self.content = content
        self.role = "assistant"


class _AnthropicChoice:
    """模擬 OpenAI response.choices[0] 物件"""
    def __init__(self, message: _AnthropicMessage):
        self.message = message
        self.index = 0
        self.finish_reason = "stop"


class _AnthropicResponse:
    """模擬 OpenAI ChatCompletion response 物件"""
    def __init__(self, content: str, input_tokens: int, output_tokens: int, model: str):
        self.choices = [_AnthropicChoice(_AnthropicMessage(content))]
        self.usage = _AnthropicUsage(input_tokens, output_tokens)
        self.model = model


class _AnthropicCompletions:
    """
    模擬 OpenAI client.chat.completions，提供 create() 方法。
    內部將 OpenAI 風格的 messages 轉換為 Anthropic SDK 的格式。
    """
    def __init__(self, anthropic_client):
        self._client = anthropic_client

    def create(self, *, model: str, messages: list, temperature: float = 1.0, **kwargs):
        """
        將 OpenAI 格式的呼叫轉換為 Anthropic SDK 呼叫。

        主要差異處理：
        1. Anthropic 的 system prompt 是獨立參數，不放在 messages 裡
        2. Anthropic 必須指定 max_tokens（OpenAI 是選填的）
        3. Anthropic 不支援 temperature=0.0，需 clamp 到 > 0
        """
        # 分離 system prompt
        system_text = ""
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                # Anthropic 支援多段 system，這裡合併為一段
                system_text += (("\n\n" if system_text else "") + msg["content"])
            else:
                api_messages.append({"role": msg["role"], "content": msg["content"]})

        # Anthropic 要求 messages 不能為空，且第一則必須是 user
        if not api_messages:
            api_messages = [{"role": "user", "content": "(empty)"}]

        # 合併連續同角色訊息（Anthropic 要求 user/assistant 嚴格交替）
        merged = []
        for msg in api_messages:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n\n" + msg["content"]
            else:
                merged.append(dict(msg))
        api_messages = merged

        # 確保第一則是 user（Anthropic 的硬性要求）
        if api_messages and api_messages[0]["role"] != "user":
            api_messages.insert(0, {"role": "user", "content": "(context follows)"})

        # Anthropic 不接受 temperature=0.0，clamp 到 0.01
        safe_temperature = max(temperature, 0.01)

        # 準備呼叫參數
        create_kwargs = {
            "model": model,
            "max_tokens": kwargs.get("max_tokens", 8192),
            "messages": api_messages,
            "temperature": safe_temperature,
        }
        
        # 只有在有 system prompt 時才加入 system 參數
        if system_text:
            create_kwargs["system"] = system_text

        # 呼叫 Anthropic API
        response = self._client.messages.create(**create_kwargs)

        # 提取回應文字（Anthropic 回傳的是 content blocks 列表）
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return _AnthropicResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=model,
        )


class _AnthropicChat:
    """模擬 OpenAI client.chat，提供 completions 屬性"""
    def __init__(self, anthropic_client):
        self.completions = _AnthropicCompletions(anthropic_client)


class AnthropicClientAdapter:
    """
    頂層適配器：模擬 openai.OpenAI() 的介面。
    使用方式與 openai.OpenAI() 完全相同：
        client = AnthropicClientAdapter(api_key="sk-ant-...")
        response = client.chat.completions.create(model="claude-...", messages=[...])
        print(response.choices[0].message.content)
    """
    def __init__(self, api_key: str):
        import anthropic
        self._anthropic = anthropic.Anthropic(api_key=api_key)
        self.chat = _AnthropicChat(self._anthropic)


# ---------------------------------------------------------------------------
# 公開 API：initialize_client
# ---------------------------------------------------------------------------

def initialize_client(api_mode: str, api_key: str):
    """
    根據模式和金鑰初始化 AI client

    Args:
        api_mode: API 模式 ("Gemini", "OpenAI 官方", "交大伺服器", "Claude")
        api_key: API 金鑰

    Returns:
        具備 client.chat.completions.create() 介面的 client 物件

    Examples:
        >>> client = initialize_client("Gemini", "your_api_key")
        >>> client = initialize_client("OpenAI 官方", "your_api_key")
        >>> client = initialize_client("Claude", "sk-ant-xxx")
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
    elif api_mode == "Claude":
        return AnthropicClientAdapter(api_key=api_key)
    else:  # OpenAI 官方
        return openai.OpenAI(api_key=api_key)
