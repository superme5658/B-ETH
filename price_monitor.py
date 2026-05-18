import asyncio
import json
import threading
import time
from datetime import datetime
import websockets
from strategy import BreakoutStrategy
from feishu_bot import FeishuBot


class MultiSymbolMonitor:
    """多币种 OKX WebSocket 实时监控 - 优化版"""
    
    def __init__(self, symbols: list, feishu_bot: FeishuBot):
        self.symbols = symbols
        self.bot = feishu_bot
        
        self.strategies = {}
        self.latest_prices = {}
        self.price_timestamp = {}  # 记录价格更新时间
        
        for symbol in symbols:
            self.strategies[symbol] = BreakoutStrategy(symbol)
            self.latest_prices[symbol] = None
            self.price_timestamp[symbol] = 0
        
        self.check_interval = 300  # 5分钟
        
        # WebSocket 重连配置
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        
        # 价格跟踪
        self.price_history = {symbol: [] for symbol in symbols}
        self.last_alert_time = {symbol: 0 for symbol in symbols}
        self.alert_cooldown = 600
        self.volatility_threshold = 2.0  # 波动告警阈值 %
        
    def get_okx_symbol(self, symbol: str) -> str:
        return f"{symbol}-USDT"
    
    def is_price_fresh(self, symbol: str, max_age_seconds: int = 120) -> bool:
        """检查价格是否新鲜（不超过2分钟）"""
        if self.latest_prices[symbol] is None:
            return False
        age = time.time() - self.price_timestamp.get(symbol, 0)
        return age <= max_age_seconds
    
    async def connect_websocket(self):
        """连接OKX WebSocket（带指数退避重连）"""
        delay = self.reconnect_delay
        
        while True:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=30,
                    close_timeout=10
                ) as websocket:
                    print(f"✅ OKX WebSocket已连接，订阅 {len(self.symbols)} 个交易对")
                    delay = self.reconnect_delay  # 重置重连延迟
                    
                    # 批量订阅
                    subscribe_args = [
                        {"channel": "trades", "instId": self.get_okx_symbol(s)}
                        for s in self.symbols
                    ]
                    await websocket.send(json.dumps({"op": "subscribe", "args": subscribe_args}))
                    print(f"📡 已订阅: {', '.join(self.symbols)}")
                    
                    # 心跳保持
                    last_ping = time.time()
                    
                    async for message in websocket:
                        # 定期发送 ping 保持连接
                        if time.time() - last_ping > 30:
                            await websocket.ping()
                            last_ping = time.time()
                        
                        try:
                            data = json.loads(message)
                            
                            # 处理交易数据
                            if data.get('arg', {}).get('channel') == 'trades':
                                for trade in data.get('data', []):
                                    inst_id = trade.get('instId', '')
                                    for symbol in self.symbols:
                                        if inst_id == self.get_okx_symbol(symbol):
                                            price = float(trade['px'])
                                            self.latest_prices[symbol] = price
                                            self.price_timestamp[symbol] = time.time()
                                            self.check_price_volatility(symbol, price)
                                            break
                                            
                            # 处理订阅确认
                            elif data.get('event') == 'subscribe':
                                print(f"✅ 订阅确认: {data.get('arg', {}).get('instId')}")
                                
                        except json.JSONDecodeError:
                            pass
                                            
            except Exception as e:
                print(f"❌ OKX WebSocket连接错误: {e}")
                print(f"🔄 {delay}秒后重连...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)  # 指数退避
    
    def check_price_volatility(self, symbol: str, price: float):
        """检查价格波动"""
        now = time.time()
        
        self.price_history[symbol].append({'price': price, 'time': now})
        self.price_history[symbol] = [p for p in self.price_history[symbol] if now - p['time'] <= 300]
        
        if now - self.last_alert_time[symbol] < self.alert_cooldown:
            return
        
        if len(self.price_history[symbol]) >= 10:
            oldest_price = self.price_history[symbol][0]['price']
            change_pct = (price - oldest_price) / oldest_price * 100
            
            if change_pct >= self.volatility_threshold:
                self.last_alert_time[symbol] = now
                asyncio.create_task(self.send_volatility_alert(symbol, "pump", change_pct, price))
            elif change_pct <= -self.volatility_threshold:
                self.last_alert_time[symbol] = now
                asyncio.create_task(self.send_volatility_alert(symbol, "crash", change_pct, price))
    
    async def send_volatility_alert(self, symbol: str, alert_type: str, change_pct: float, price: float):
        title = f"⚡ {symbol} {'急速拉升' if alert_type == 'pump' else '急速下跌'}"
        message = f"**{title}**\n\n幅度: {change_pct:+.2f}%\n价格: ${price:,.2f}"
        await asyncio.to_thread(self.bot.send_card, "行情波动", message, "red")
    
    def strategy_check_loop(self):
        """定时检查策略（带价格新鲜度检查）"""
        while True:
            try:
                for symbol in self.symbols:
                    if not self.is_price_fresh(symbol, max_age_seconds=300):
                        print(f"[{symbol}] 价格数据过时，跳过检查")
                        continue
                    
                    current_price = self.latest_prices[symbol]
                    signal = self.strategies[symbol].check_signal(current_price)
                    
                    if signal:
                        asyncio.run_coroutine_threadsafe(
                            self.send_signal_async(signal),
                            asyncio.get_event_loop()
                        )
                        print(f"[{symbol}] ✅ 信号推送: {signal['type']} @ ${signal['price']:,.2f}")
                    else:
                        # 静默模式：不打印无信号日志，减少噪音
                        pass
                        
            except Exception as e:
                print(f"策略检查失败: {e}")
            
            time.sleep(self.check_interval)
    
    async def send_signal_async(self, signal: dict):
        await asyncio.to_thread(
            self.bot.send_card,
            f"📊 {signal['symbol']} 交易信号",
            signal['message'],
            "green" if signal['type'] == "LONG" else "red"
        )
    
    def start(self):
        print(f"🚀 启动多币种监控: {', '.join(self.symbols)}")
        
        strategy_thread = threading.Thread(target=self.strategy_check_loop, daemon=True)
        strategy_thread.start()
        
        try:
            asyncio.run(self.connect_websocket())
        except KeyboardInterrupt:
            print("监控已停止")
