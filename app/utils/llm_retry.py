"""
LLM API 调用重试与超时工具。

提供带指数退避的装饰器，包装 openai client.chat.completions.create 调用。

使用方式：
    from app.utils.llm_retry import retry_on_failure

    @retry_on_failure(max_retries=3, timeout=120)
    def call_llm(client, model, messages):
        return client.chat.completions.create(model=model, messages=messages, timeout=120)
"""

import time
import functools
from app.utils.log_config import get_logger

logger = get_logger(__name__)


def retry_on_failure(max_retries: int = 3, base_delay: float = 1.0, timeout: float = 120.0):
    """装饰器工厂：为可能失败的网络调用增加重试逻辑。

    Args:
        max_retries:  最大重试次数（含首次调用，即最多 3 次 = 1 次原始 + 2 次重试）
        base_delay:   初始退避延迟秒数，每次翻倍（1s → 2s → 4s）
        timeout:      传给底层 API 调用的超时秒数（仅当函数签名接受 timeout 时生效）

    Returns:
        装饰后的函数，功能与原函数相同。
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            delay = base_delay

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(f"第 {attempt}/{max_retries} 次调用失败: {e}，{delay:.0f}s 后重试...")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        logger.error(f"重试 {max_retries} 次后仍然失败: {e}")
                        raise last_exception

            # 理论上不会到达这里
            raise last_exception

        return wrapper
    return decorator
