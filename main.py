import os
import asyncio
from fastapi import FastAPI
from contextlib import asynccontextmanager
from feishu_bot import FeishuBot
from price_monitor import MultiSymbolMonitor
import threading

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK_URL")
FEISHU_SECRET = os.environ.get("FEISHU_SECRET")
SYMBOLS = os.environ.get("SYMBOLS", "BTC,ETH").split(",")
SYMBOLS = [s.strip().upper() for s in SYMBOLS]

VOLATILITY_THRESHOLD = float(os.environ.get("VOLATILITY_THRESHOLD", "2.0"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "300"))

bot = FeishuBot(FEISHU_WEBHOOK, FEISHU_SECRET)
monitor = MultiSymbolMonitor(SYMBOLS, bot)
monitor.volatility_threshold = VOLATILITY_THRESHOLD
monitor.check_interval = CHECK_INTERVAL


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"🚀 启动监控: {', '.join(SYMBOLS)}")
    thread = threading.Thread(target=monitor.start, daemon=True)
    thread.start()
    
    await asyncio.to_thread(
        bot.send_text,
        f"🤖 **多币种信号监控机器人已启动**\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **监控配置**\n"
        f"  • 交易对: {', '.join(SYMBOLS)}/USDT\n"
        f"  • 数据源: OKX\n"
        f"  • 策略: 4H + 30min 突破策略（2次确认）\n"
        f"  • 检查频率: 每{CHECK_INTERVAL}秒\n"
        f"  • 波动告警: {VOLATILITY_THRESHOLD}%\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ 系统运行正常，等待信号触发..."
    )
    print("✅ 机器人已启动")
    yield
    print("关闭中...")


app = FastAPI(title="Crypto Signal Bot", lifespan=lifespan)


@app.get("/")
def root():
    return {
        "status": "running",
        "symbols": SYMBOLS,
        "exchange": "OKX",
        "strategy": "4H + 30min Breakout (2 confirmations)",
        "check_interval_seconds": CHECK_INTERVAL,
        "volatility_threshold": VOLATILITY_THRESHOLD,
        "latest_prices": monitor.latest_prices,
        "price_freshness": {
            s: monitor.is_price_fresh(s) for s in SYMBOLS
        }
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "symbols": SYMBOLS,
        "latest_prices": monitor.latest_prices,
        "price_fresh": {s: monitor.is_price_fresh(s) for s in SYMBOLS}
    }


@app.get("/status/{symbol}")
def symbol_status(symbol: str):
    """查看单个币种的策略状态"""
    symbol = symbol.upper()
    if symbol not in SYMBOLS:
        return {"error": f"{symbol} 不在监控列表中", "available": SYMBOLS}
    
    strategy = monitor.strategies.get(symbol)
    if not strategy:
        return {"error": "策略未初始化"}
    
    return {
        "symbol": symbol,
        "latest_price": monitor.latest_prices.get(symbol),
        "price_fresh": monitor.is_price_fresh(symbol),
        "confirmation_count": strategy.confirmation_count,
        "last_signal_key": strategy.last_signal_key
    }


@app.post("/test")
def test_push():
    result = bot.send_card(
        "✅ 测试消息",
        f"多币种机器人运行正常\n\n"
        f"监控: {', '.join(SYMBOLS)}\n"
        f"波动阈值: {VOLATILITY_THRESHOLD}%\n"
        f"检查间隔: {CHECK_INTERVAL}秒\n"
        f"信号确认: 2次\n\n"
        f"策略已就绪，等待信号",
        "green"
    )
    return result
