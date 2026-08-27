"""Token estimation helpers used before provider responses return usage metadata."""


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token for English text)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict[str, str]]) -> int:
    """Estimate total tokens across a message list."""
    overhead_per_message = 4
    return sum(estimate_tokens(message.get("content", "")) + overhead_per_message for message in messages)
