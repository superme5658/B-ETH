import os
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from feishu_bot import FeishuBot
from price_monitor import SignalMonitor
import threading

# 从环境变量读取配置
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK_URL")
FEISHU_SECRET = os.environ.get("FEISHU_SECRET")
SYMBOL = os.environ.get("SYMBOL", "BTC")

# 初始化飞书机器人
bot = FeishuBot(FEISHU_WEBHOOK, FEISHU_SECRET)

# 全局监控器
monitor = SignalMonitor(SYMBOL, bot)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print("正在启动监控机器人...")
    thread = threading.Thread(target=monitor.start, daemon=True)
    thread.start()
    
    # 发送启动通知
    await asyncio.to_thread(
        bot.send_text,
        f"🤖 **信号监控机器人已启动**\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **监控配置**\n"
        f"  • 交易对: {SYMBOL}/USDT\n"
        f"  • 数据源: OKX\n"
        f"  • 策略: 4H + 30min 突破策略\n"
        f"  • 检查频率: 每5分钟\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ 系统运行正常，等待信号触发..."
    )
    print("机器人已启动")
    
    yield
    
    print("正在关闭...")


app = FastAPI(title="Crypto Signal Bot - OKX", lifespan=lifespan)


@app.get("/")
def root():
    return {
        "status": "running",
        "symbol": SYMBOL,
        "exchange": "OKX",
        "strategy": "4H + 30min Breakout",
        "check_interval": "300 seconds",
        "message": "信号监控中"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "symbol": SYMBOL,
        "exchange": "OKX",
        "latest_price": monitor.latest_price
    }


@app.post("/test")
def test_push():
    """测试飞书推送"""
    result = bot.send_card(
        "✅ 测试消息", 
        f"机器人运行正常\n\n交易对: {SYMBOL}/USDT\n数据源: OKX\n检查频率: 每5分钟\n策略已就绪，等待信号", 
        "green"
    )
    return result
