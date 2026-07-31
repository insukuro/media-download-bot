# src/adapters/vk/keyboards.py
from typing import List, Dict, Any
import json


class VKKeyboard:
    """Генератор клавиатур для VK"""
    
    @staticmethod
    def create_inline(buttons: List[List[Dict[str, Any]]]) -> str:
        """
        Создает inline клавиатуру для VK
        
        buttons = [
            [
                {"text": "360p", "callback": "dl:key:360p:video", "color": "primary"},
                {"text": "720p", "callback": "dl:key:720p:video", "color": "positive"}
            ],
            [
                {"text": "Аудио 320kbps", "callback": "dl:key:320kbps:audio", "color": "secondary"}
            ]
        ]
        """
        keyboard = {
            "inline": True,
            "buttons": []
        }
        
        for row in buttons:
            keyboard_row = []
            for btn in row:
                action = {
                    "type": "callback",
                    "label": btn["text"],
                    "payload": json.dumps({"callback": btn["callback"]})
                }
                keyboard_btn = {
                    "action": action,
                    "color": btn.get("color", "primary")
                }
                keyboard_row.append(keyboard_btn)
            keyboard["buttons"].append(keyboard_row)
        
        return json.dumps(keyboard)


# Вспомогательный класс для формирования кнопок
class VKButton:
    @staticmethod
    def callback(text: str, callback_data: str, color: str = "primary") -> Dict:
        return {
            "text": text,
            "callback": callback_data,
            "color": color
        }