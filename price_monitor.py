import asyncio
import json
import threading
import time
from datetime import datetime
import websockets
import requests
import os
import hmac
import base64
import hashlib
from strategy import BreakoutStrategy
from feishu_bot import FeishuBot


class SignalMonitor:
    """OKX WebSocket实时监控价格并触发策略判断"""
    
    def __init__(self, symbol: str, feishu_bot: FeishuBot):
        self.symbol = symbol.upper()
        self.bot = feishu_bot
        self.strategy = BreakoutStrategy(symbol)
        self.latest_price = None
        
        # OKX 配置 - 交易对格式: BTC-USDT
        self.okx_symbol = f"{self.symbol}-USDT"
        self.check_interval = 60
        
        # OKX WebSocket URL
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        
        # 价格跟踪（用于波动告警）
        self.price_history = []
        self.last_alert_time = 0
        self.alert_cooldown = 600
        
    async def connect_websocket(self):
        """连接OKX WebSocket获取实时价格"""
        while True:
            try:
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=30
                ) as websocket:
                    print(f"OKX WebSocket已连接，订阅 {self.okx_symbol} 交易数据")
                    
                    # 订阅实时交易数据
                    subscribe_msg = {
                        "op": "subscribe",
                        "args": [{
                            "channel": "trades",
                            "instId": self.okx_symbol
                        }]
                    }
                    await websocket.send(json.dumps(subscribe_msg))
                    print(f"已订阅 {self.okx_symbol} 实时交易")
                    
                    # 处理消息
                    async for message in websocket:
                        data = json.loads(message)
                        
                        # 检查是否是交易数据
                        if 'data' in data and isinstance(data['data'], list):
                            for trade in data['data']:
                                if 'px' in trade:
                                    price = float(trade['px'])
                                    self.latest_price = price
                                    self.check_price_volatility(price)
                                    
            except Exception as e:
                print(f"OKX WebSocket连接错误: {e}")
                await asyncio.sleep(5)  # 等待5秒后重连
    
    def check_price_volatility(self, price: float):
        """检查价格波动，超过阈值发送告警"""
        now = time.time()
        
        # 记录价格
        self.price_history.append({
            'price': price,
            'time': now
        })
        
        # 清理5分钟前的记录
        self.price_history = [p for p in self.price_history if now - p['time'] <= 300]
        
        # 如果冷却期内，不发送告警
        if now - self.last_alert_time < self.alert_cooldown:
            return
        
        # 计算5分钟涨跌幅
        if len(self.price_history) >= 10:  # 至少10个数据点
            oldest_price = self.price_history[0]['price']
            change_pct = (price - oldest_price) / oldest_price * 100
            
            if change_pct >= 2.0:  # 2%上涨
                self.last_alert_time = now
                asyncio.create_task(self.send_volatility_alert("pump", change_pct, price))
            elif change_pct <= -2.0:  # 2%下跌
                self.last_alert_time = now
                asyncio.create_task(self.send_volatility_alert("crash", change_pct, price))
    
    async def send_volatility_alert(self, alert_type: str, change_pct: float, price: float):
        """发送波动告警"""
        if alert_type == "pump":
            title = "⚡ 急速拉升"
            color = "red"
        else:
            title = "⚡ 急速下跌"
            color = "red"
        
        message = f"**{title}**\n\n幅度: {change_pct:+.2f}%\n价格: ${price:,.2f}"
        await asyncio.to_thread(self.bot.send_card, "行情波动", message, color)
    
    def strategy_check_loop(self):
        """定时执行策略检查（在独立线程中运行）"""
        while True:
            try:
                if self.latest_price:
                    signal = self.strategy.check_signal(self.latest_price)
                    if signal:
                        # 发送策略信号到飞书
                        asyncio.run_coroutine_threadsafe(
                            self.send_signal_async(signal),
                            asyncio.get_event_loop()
                        )
                        print(f"信号已推送: {signal['type']} at ${signal['price']}")
                else:
                    print("等待价格数据...")
            except Exception as e:
                print(f"策略检查失败: {e}")
            
            time.sleep(self.check_interval)
    
    async def send_signal_async(self, signal: dict):
        """异步发送信号"""
        await asyncio.to_thread(
            self.bot.send_card,
            f"📊 {self.symbol} 交易信号",
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
