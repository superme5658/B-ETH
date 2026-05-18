import hmac
import base64
import hashlib
import requests
from datetime import datetime
from typing import Optional

class FeishuBot:
    def __init__(self, webhook_url: str, secret: Optional[str] = None):
        self.webhook_url = webhook_url
        self.secret = secret

    def _gen_sign(self, timestamp: int) -> str:
        """生成签名校验（如开启签名校验）"""
        if not self.secret:
            return ""
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def send_text(self, text: str) -> dict:
        """发送文本消息"""
        timestamp = int(datetime.now().timestamp())
        payload = {
            "msg_type": "text",
            "content": {"text": text},
            "timestamp": str(timestamp)
        }
        if self.secret:
            payload["sign"] = self._gen_sign(timestamp)

        response = requests.post(
            self.webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        return response.json()

    def send_card(self, title: str, content: str, color: str = "blue") -> dict:
        """发送卡片消息，更美观"""
        timestamp = int(datetime.now().timestamp())
        
        color_map = {
            "red": "red",
            "green": "green", 
            "blue": "blue",
            "yellow": "yellow"
        }
        
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color_map.get(color, "blue")
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": content}
                    },
                    {
                        "tag": "hr"
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {"tag": "plain_text", "content": f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                        ]
                    }
                ]
            },
            "timestamp": str(timestamp)
        }
        
        if self.secret:
            payload["sign"] = self._gen_sign(timestamp)
            
        response = requests.post(
            self.webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        return response.json()