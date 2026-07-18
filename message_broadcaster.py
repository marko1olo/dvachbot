from dataclasses import dataclass
from typing import Any, Set, Dict, Optional

@dataclass
class BroadcasterConfig:
    bot_instance: Any
    board_id: str
    recipients: Set[int]
    content: Dict[str, Any]
    reply_info: Optional[Dict[str, Any]] = None
    keyboard: Optional[Any] = None
    verbose: bool = False
    queue_enqueued_at: Optional[float] = None
    queue_wait_sec: Optional[float] = None
    delivery_phase: str = "full"
    delivery_original_recipients: Optional[int] = None
    delivery_deferred_recipients: int = 0


class MessageBroadcaster:
    def __init__(self, config: BroadcasterConfig):
        self.config = config
        self.bot_instance = config.bot_instance
        self.board_id = config.board_id
        self.recipients = config.recipients
        self.content = config.content
        self.reply_info = config.reply_info
        self.keyboard = config.keyboard
        self.verbose = config.verbose
        self.queue_enqueued_at = config.queue_enqueued_at
        self.queue_wait_sec = config.queue_wait_sec
        self.delivery_phase = config.delivery_phase
        self.delivery_original_recipients = config.delivery_original_recipients
        self.delivery_deferred_recipients = config.delivery_deferred_recipients