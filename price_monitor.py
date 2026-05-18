import threading
import time
import json
from priceflare import Sentinel, parsers
from strategy import BreakoutStrategy
from feishu_bot import FeishuBot

class SignalMonitor:
    """使用PriceFlare实时监控价格并触发策略判断"""
    
    def __init__(self, symbol: str, feishu_bot: FeishuBot):
        self.symbol = symbol.lower()
        self.bot = feishu_bot
        self.strategy = BreakoutStrategy(symbol)
        
        # Binance WebSocket URL
        self.ws_url = f"wss://stream.binance.com:9443/ws/{self.symbol}usdt@trade"
        
        # 价格缓存
        self.latest_price = None
        self.check_interval = 60  # 每60秒检查一次策略（30min/4H周期不需要高频）
        
    def on_price_update(self, price: float):
        """价格更新回调"""
        self.latest_price = price
        
    def on_alert(self, alert: dict):
        """PriceFlare告警回调（快速波动通知）"""
        alert_type = alert['type']
        change_pct = alert['change_pct']
        
        # 快速波动时发送通知（可选，不是策略信号）
        message = f"⚡ **波动告警**\n\n类型: {alert_type}\n幅度: {change_pct:+.2f}%\n价格: ${alert['cur_price']:,.2f}"
        self.bot.send_card("行情波动", message, "yellow")
        
    def strategy_loop(self):
        """定时执行策略检查"""
        while True:
            try:
                if self.latest_price:
                    signal = self.strategy.check_signal()
                    if signal:
                        # 发送策略信号到飞书
                        self.bot.send_card(
                            f"📊 {self.symbol.upper()} 交易信号",
                            signal['message'],
                            "green" if signal['type'] == "LONG" else "red"
                        )
                        print(f"信号已推送: {signal['type']} at ${signal['price']}")
            except Exception as e:
                print(f"策略检查失败: {e}")
            
            time.sleep(self.check_interval)
    
    def start(self):
        """启动监控"""
        # 启动策略检查线程
        strategy_thread = threading.Thread(target=self.strategy_loop, daemon=True)
        strategy_thread.start()
        
        # 启动PriceFlare实时监控
        sentinel = Sentinel(
            ws_url=self.ws_url,
            price_parser=parsers.binance,
            crash_threshold=2.0,   # 2%下跌触发告警
            pump_threshold=2.0,    # 2%上涨触发告警
            window_seconds=300,    # 5分钟窗口
            cooldown_seconds=600,  # 10分钟冷却
            on_pump=self.on_price_update,
            on_crash=self.on_price_update,
            on_alert=self.on_alert
        )
        
        print(f"开始监控 {self.symbol.upper()}...")
        sentinel.start()
        
        # 保持运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sentinel.stop()
            print("监控已停止")