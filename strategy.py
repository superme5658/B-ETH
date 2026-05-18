import ccxt
import pandas as pd
from datetime import datetime
from typing import Dict, Optional


class BreakoutStrategy:
    """4H/30min 突破策略"""
    
    def __init__(self, symbol: str = "BTC/USDT"):
        self.symbol = f"{symbol}/USDT"
        self.exchange = ccxt.binance()
        
        # 存储前高前低数据
        self.h4_high = None
        self.h4_low = None
        self.m30_high = None
        self.m30_low = None
        self.last_signal_time = None  # 避免重复推送
        
    def fetch_ohlcv_data(self, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """获取K线数据"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                self.symbol,
                timeframe=timeframe,
                limit=limit
            )
            
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"获取{timeframe}K线数据失败: {e}")
            return pd.DataFrame()
    
    def get_prev_period_high_low(self, timeframe: str) -> tuple:
        """获取前一个完整周期的最高点和最低点"""
        df = self.fetch_ohlcv_data(timeframe)
        if df.empty or len(df) < 2:
            return None, None
        
        # 使用前一根完整K线（排除当前未完成的）
        prev_candle = df.iloc[-2]
        return prev_candle['high'], prev_candle['low']
    
    def check_signal(self, current_price: float) -> Optional[Dict]:
        """检查是否有交易信号"""
        # 获取4H周期数据
        h4_high, h4_low = self.get_prev_period_high_low('4h')
        # 获取30分钟周期数据
        m30_high, m30_low = self.get_prev_period_high_low('30m')
        
        if not h4_high or not m30_high:
            return None
        
        signal = None
        
        # 做多信号：4H突破前高 + 30min突破前高
        # 使用0.1%的过滤阈值避免假突破
        h4_broken = current_price > h4_high * 1.001
        m30_broken = current_price > m30_high * 1.001
        
        if h4_broken and m30_broken:
            # 检查是否重复推送（同一小时周期内不重复）
            current_hour = datetime.now().strftime('%Y%m%d%H')
            signal_key = f"LONG_{current_hour}"
            
            if self.last_signal_time != signal_key:
                self.last_signal_time = signal_key
                signal = {
                    "type": "LONG",
                    "price": current_price,
                    "h4_high": h4_high,
                    "m30_high": m30_high,
                    "message": f"🟢 **做多信号**\n\n"
                               f"• 4H前高: ${h4_high:,.2f} ✅已突破\n"
                               f"• 30min前高: ${m30_high:,.2f} ✅已突破\n"
                               f"• 当前价格: ${current_price:,.2f}\n\n"
                               f"**建议**：回踩30min前高附近入场，止损设在前低下方"
                }
        
        # 做空信号：4H跌破前低 + 30min跌破前低
        if h4_low and m30_low:
            h4_broken_down = current_price < h4_low * 0.999
            m30_broken_down = current_price < m30_low * 0.999
            
            if h4_broken_down and m30_broken_down:
                current_hour = datetime.now().strftime('%Y%m%d%H')
                signal_key = f"SHORT_{current_hour}"
                
                if self.last_signal_time != signal_key:
                    self.last_signal_time = signal_key
                    signal = {
                        "type": "SHORT",
                        "price": current_price,
                        "message": f"🔴 **做空信号**\n\n"
                                   f"• 4H前低: ${h4_low:,.2f} ✅已跌破\n"
                                   f"• 30min前低: ${m30_low:,.2f} ✅已跌破\n"
                                   f"• 当前价格: ${current_price:,.2f}\n\n"
                                   f"**建议**：反弹30min前低附近入场，止损设在前高上方"
                    }
        
        return signal
