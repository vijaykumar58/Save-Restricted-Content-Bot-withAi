from pyrogram import filters
from typing import Dict, Optional, Union

# Use a more specific type annotation
user_steps: Dict[int, str] = {}  # {user_id: step}

def login_filter_func(_, __, message) -> bool:
    """Custom filter to check if user is in login process."""
    if not message or not message.from_user:
        return False
    return message.from_user.id in user_steps

login_in_progress = filters.create(login_filter_func, name="LoginInProgressFilter")

def set_user_step(user_id: int, step: Optional[str] = None) -> None:
    """
    Set or clear user's current step.
    Args:
        user_id: Telegram user ID
        step: If provided, sets the step. If None, clears the step.
    """
    if step:
        user_steps[user_id] = step
    else:
        user_steps.pop(user_id, None)

def get_user_step(user_id: int) -> Optional[str]:
    """Get user's current step or None if no step is set."""
    return user_steps.get(user_id)