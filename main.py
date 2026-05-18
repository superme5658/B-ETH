import os
from fastapi import FastAPI
from feishu_bot import FeishuBot
from price_monitor import SignalMonitor
import threading

app = FastAPI()

# 从环境变量读取配置
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK_URL")
FEISHU_SECRET = os.environ.get("FEISHU_SECRET")  # 可选，开启签名校验时需要
SYMBOL = os.environ.get("SYMBOL", "BTC")  # BTC 或 ETH

# 初始化飞书机器人
bot = FeishuBot(FEISHU_WEBHOOK, FEISHU_SECRET)

# 启动监控线程
monitor = SignalMonitor(SYMBOL, bot)

@app.on_event("startup")
def startup_event():
    """服务启动时自动开启监控"""
    thread = threading.Thread(target=monitor.start, daemon=True)
    thread.start()
    bot.send_text(f"🤖 信号监控机器人已启动\n\n正在监控: {SYMBOL}/USDT\n策略: 4H/30min突破策略")

@app.get("/")
def root():
    return {"status": "running", "symbol": SYMBOL, "message": "信号监控中"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.post("/test")
def test_push():
    """测试飞书推送"""
    result = bot.send_card("测试消息", "机器人运行正常 ✅", "green")
    return result