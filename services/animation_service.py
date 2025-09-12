import random

ANIMATIONS = {
    "dots": ["⠁","⠂","⠄","⡀","⢀","⠠","⠐","⠈"],
    "typing": ["✏️","✏️.","✏️..","✏️..."],
    "moon": ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"],
    "magic": ["🔮","✨","💫","🌟","💫","✨"],
    "spark": ["⚡","✨","💥","✨"],
    "heart": ["💓","💗","💖","💗"],
}

def send_simple_animation(bot, chat_id, text="Генерирую ответ...", max_frames=4, reply_to_message_id=None):
    """
    Отправляет в чат одно сообщение с несколькими эмоджи из случайной анимации и текстом.
    Возвращает id сообщения.
    """
    name, frames = random.choice(list(ANIMATIONS.items()))
    unique_frames = frames[:max_frames]
    animation_str = "".join(unique_frames)
    msg = bot.send_message(
        chat_id,
        f"{animation_str} {text}",
        reply_to_message_id=reply_to_message_id,
    )
    return msg.id
