from pyrogram import filters
from pyrogram.types import Message # For type hinting

user_steps: dict = {} # Type hint for clarity

# The filter function signature expects client, filter, and update (message)
def login_filter_func(_, __, message: Message) -> bool:
    if message.from_user: # Ensure from_user exists
        user_id = message.from_user.id
        return user_id in user_steps
    return False

login_in_progress = filters.create(login_filter_func)

def set_user_step(user_id: int, step: any = None): # step can be anything, e.g., int or str
    if step is not None: # Check against None explicitly
        user_steps[user_id] = step
    else:
        user_steps.pop(user_id, None) # Safely remove if exists


def get_user_step(user_id: int) -> any: # Return type can be varied
    return user_steps.get(user_id)
