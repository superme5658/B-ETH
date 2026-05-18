import asyncio
import json
import threading
import time
from datetime import datetime
import websockets
from strategy import BreakoutStrategy
from feishu_bot import FeishuBot


class MultiSymbolMonitor:
    """多币种 OKX WebSocket 实时监控"""
    
    def __init__(self, symbols: list, feishu_bot: FeishuBot):
        self.symbols = symbols  # ['BTC', 'ETH']
        self.bot = feishu_bot
        
        # 为每个币种创建策略实例和价格缓存
        self.strategies = {}
        self.latest_prices = {}
        
        for symbol in symbols:
            self.strategies[symbol] = BreakoutStrategy(symbol)
            self.latest_prices[symbol] = None
        
        self.check_interval = 300  # 每5分钟检查一次
        
        # OKX WebSocket URL
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        
        # 价格跟踪（用于波动告警）
        self.price_history = {symbol: [] for symbol in symbols}
        self.last_alert_time = {symbol: 0 for symbol in symbols}
        self.alert_cooldown = 600  # 10分钟冷却
        
    def get_okx_symbol(self, symbol: str) -> str:
        """转换为 OKX 格式"""
        return f"{symbol}-USDT"
    
    async def connect_websocket(self):
        """连接OKX WebSocket，订阅多个币种"""
        while True:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=30
                ) as websocket:
                    print(f"OKX WebSocket已连接，订阅 {len(self.symbols)} 个交易对")
                    
                    # 订阅所有币种的实时交易数据
                    subscribe_args = []
                    for symbol in self.symbols:
                        subscribe_args.append({
                            "channel": "trades",
                            "instId": self.get_okx_symbol(symbol)
                        })
                    
                    subscribe_msg = {
                        "op": "subscribe",
                        "args": subscribe_args
                    }
                    await websocket.send(json.dumps(subscribe_msg))
                    print(f"已订阅: {', '.join(self.symbols)}")
                    
                    # 处理消息
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            
                            if 'data' in data and isinstance(data['data'], list):
                                for trade in data['data']:
                                    if 'px' in trade and 'instId' in trade:
                                        # 从 instId 提取币种 (BTC-USDT -> BTC)
                                        inst_id = trade['instId']
                                        for symbol in self.symbols:
                                            if inst_id == self.get_okx_symbol(symbol):
                                                price = float(trade['px'])
                                                self.latest_prices[symbol] = price
                                                self.check_price_volatility(symbol, price)
                                                break
                        except json.JSONDecodeError:
                            pass
                                            
            except Exception as e:
                print(f"OKX WebSocket连接错误: {e}")
                await asyncio.sleep(5)
    
    def check_price_volatility(self, symbol: str, price: float):
        """检查价格波动"""
        now = time.time()
        
        # 记录价格
        self.price_history[symbol].append({'price': price, 'time': now})
        
        # 清理5分钟前的记录
        self.price_history[symbol] = [p for p in self.price_history[symbol] if now - p['time'] <= 300]
        
        # 如果冷却期内，不发送告警
        if now - self.last_alert_time[symbol] < self.alert_cooldown:
            return
        
        # 计算5分钟涨跌幅
        if len(self.price_history[symbol]) >= 10:
            oldest_price = self.price_history[symbol][0]['price']
            change_pct = (price - oldest_price) / oldest_price * 100
            
            if change_pct >= 2.0:
                self.last_alert_time[symbol] = now
                asyncio.create_task(self.send_volatility_alert(symbol, "pump", change_pct, price))
            elif change_pct <= -2.0:
                self.last_alert_time[symbol] = now
                asyncio.create_task(self.send_volatility_alert(symbol, "crash", change_pct, price))
    
    async def send_volatility_alert(self, symbol: str, alert_type: str, change_pct: float, price: float):
        """发送波动告警"""
        if alert_type == "pump":
            title = f"⚡ {symbol} 急速拉升"
            color = "red"
        else:
            title = f"⚡ {symbol} 急速下跌"
            color = "red"
        
        message = f"**{title}**\n\n幅度: {change_pct:+.2f}%\n价格: ${price:,.2f}"
        await asyncio.to_thread(self.bot.send_card, "行情波动", message, color)
    
    def strategy_check_loop(self):
        """定时检查所有币种的策略信号"""
        while True:
            try:
                for symbol in self.symbols:
                    current_price = self.latest_prices.get(symbol)
                    if current_price:
                        strategy = self.strategies[symbol]
                        signal = strategy.check_signal(current_price)
                        if signal:
                            asyncio.run_coroutine_threadsafe(
                                self.send_signal_async(signal),
                                asyncio.get_event_loop()
                            )
                            print(f"[{symbol}] 信号已推送: {signal['type']} at ${signal['price']}")
                        else:
                            # 可选：打印日志（每5分钟一次，多币种会有点多，可以注释掉）
                            pass
                    else:
                        print(f"[{symbol}] 等待价格数据...")
            except Exception as e:
                print(f"策略检查失败: {e}")
            
            time.sleep(self.check_interval)
    
    async def send_signal_async(self, signal: dict):
        """异步发送信号"""
        await asyncio.to_thread(
            self.bot.send_card,
            f"📊 {signal['symbol']} 交易信号",
            signal['message'],
            "green" if signal['type'] == "LONG" else "red"
        )
    
    def start(self):
        """启动监控"""
        # 启动策略检查线程
        strategy_thread = threading.Thread(target=self.strategy_check_loop, daemon=True)
        strategy_thread.start()
        
        # 启动WebSocket事件循环
        try:
            asyncio.run(self.connect_websocket())
        except KeyboardInterrupt:
            print("监控已停止")
