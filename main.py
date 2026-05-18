import os
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from feishu_bot import FeishuBot
from price_monitor import MultiSymbolMonitor
import threading

# 从环境变量读取配置
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK_URL")
FEISHU_SECRET = os.environ.get("FEISHU_SECRET")

# 监控的币种列表（可配置）
SYMBOLS = os.environ.get("SYMBOLS", "BTC,ETH").split(",")
SYMBOLS = [s.strip().upper() for s in SYMBOLS]

# 初始化飞书机器人
bot = FeishuBot(FEISHU_WEBHOOK, FEISHU_SECRET)

# 全局监控器
monitor = MultiSymbolMonitor(SYMBOLS, bot)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print(f"正在启动多币种监控机器人... 监控: {', '.join(SYMBOLS)}")
    thread = threading.Thread(target=monitor.start, daemon=True)
    thread.start()
    
    # 发送启动通知
    await asyncio.to_thread(
        bot.send_text,
        f"🤖 **多币种信号监控机器人已启动**\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **监控配置**\n"
        f"  • 交易对: {', '.join(SYMBOLS)}/USDT\n"
        f"  • 数据源: OKX\n"
        f"  • 策略: 4H + 30min 突破策略\n"
        f"  • 检查频率: 每5分钟\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ 系统运行正常，等待信号触发..."
    )
    print("机器人已启动")
    
    yield
    
    print("正在关闭...")


app = FastAPI(title="Crypto Signal Bot - Multi Symbol", lifespan=lifespan)


@app.get("/")
def root():
    return {
        "status": "running",
        "symbols": SYMBOLS,
        "exchange": "OKX",
        "strategy": "4H + 30min Breakout",
        "check_interval": "300 seconds",
        "latest_prices": monitor.latest_prices,
        "message": "多币种信号监控中"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "symbols": SYMBOLS,
        "exchange": "OKX",
        "latest_prices": monitor.latest_prices
    }


@app.post("/test")
def test_push():
    """测试飞书推送"""
    result = bot.send_card(
        "✅ 测试消息", 
        f"多币种机器人运行正常\n\n监控: {', '.join(SYMBOLS)}/USDT\n数据源: OKX\n检查频率: 每5分钟\n策略已就绪，等待信号", 
        "green"
    )
    return result


@app.post("/add/{symbol}")
def add_symbol(symbol: str):
    """动态添加监控币种（可选功能）"""
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        SYMBOLS.append(symbol)
        # 需要重启才能生效，这里只是演示
        return {"message": f"已添加 {symbol}，需要重启服务生效"}
    return {"message": f"{symbol} 已在监控列表中"}
