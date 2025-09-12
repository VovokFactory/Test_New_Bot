import random
import time
import threading
from contextlib import contextmanager

# 🎨 Большая коллекция анимаций
ANIMATIONS = {
    "moon": ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"],
    "space": ["🚀","🪐","🌌","✨","☄️","🌌"],
    "satellite": ["📡","🛰️","📡","🛰️"],
    "bars": ["▁","▃","▅","▇","█","▇","▅","▃"],
    "dots": ["⠁","⠂","⠄","⡀","⢀","⠠","⠐","⠈"],
    "blocks": ["□","◱","◧","▣","■","◧","◱"],
    "sparks": ["⚡","✨","💥","✨"],
    "magic": ["🔮","✨","💫","🌟","💫","✨"],
    "crystals": ["🔹","🔷","💎","🔷","🔹"],
    "typing": ["✏️","✏️.","✏️..","✏️..."],
    "keyboard": ["⌨️","⌨️.","⌨️..","⌨️..."],
    "robot": ["🤖","🤖💭","🤖🧠","🤖💭"],
    "cpu": ["💻","🖥️","🖲️","💻"],
    "matrix": ["🟩","🟩🟩","🟩🟩🟩","🟩🟩🟩🟩","🟩🟩🟩","🟩🟩","🟩"],
    "binary": ["0️⃣","1️⃣","0️⃣","1️⃣"],
    "lab": ["🧪","⚗️","🧫","🔬","🧬"],
    "chemistry": ["⚗️","🧪","⚗️","🧪"],
    "weather": ["☀️","⛅","☁️","🌧️","🌩️","🌙"],
    "fire": ["🔥","💨","🔥","💨"],
    "snail": ["🐌","🐢","🐌","🐢"],
    "hamster": ["🐹","💭","🐹","💭"],
    "coffee": ["☕","💭","☕","💭"],
    "spheres": ["⚪","⚫","⚪","⚫"],
    "arrows": ["⬆️","➡️","⬇️","⬅️"],
    "compass": ["🧭","🧭.","🧭..","🧭..."],
    "heart": ["💓","💗","💖","💗"],
    "smile": ["🙂","😊","😃","😊"],
}

_last_animation = None

def _get_random_animation():
    """Выбирает случайную анимацию, избегая повтора последней."""
    global _last_animation
    available = list(ANIMATIONS.items())
    if _last_animation:
        available = [(k, v) for k, v in available if k != _last_animation]
    name, frames = random.choice(available)
    _last_animation = name
    return name, frames

def _start_animation(bot, chat_id, text="Думаю...", delay=0.4, reply_to_message_id=None):
    """
    Внутренняя функция запуска анимации.
    Если reply_to_message_id указан, сообщение будет ответом на это сообщение.
    """
    name, frames = _get_random_animation()
    msg = bot.send_message(
        chat_id,
        f"{frames[0]} {text}",
        reply_to_message_id=reply_to_message_id
    )
    stop_event = threading.Event()

    def _animate():
        i = 0
        while not stop_event.is_set():
            try:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg.id,
                    text=f"{frames[i]} {text}"
                )
            except:
                # Если сообщение удалено или возникла другая ошибка — прекращаем анимацию
                break
            i = (i + 1) % len(frames)
            time.sleep(delay)

    threading.Thread(target=_animate, daemon=True).start()
    return stop_event, msg.id

@contextmanager
def thinking_animation(bot, chat_id, text="Думаю...", delay=0.4, reply_to_message_id=None):
    """
    Контекстный менеджер для анимации.
    Пример использования:
        with thinking_animation(bot, chat_id, reply_to_message_id=message.id):
            answer = generate_model_response(...)
    """
    stop_event, msg_id = _start_animation(bot, chat_id, text, delay, reply_to_message_id)
    try:
        yield
    finally:
        stop_event.set()
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass
