import ccxt
import pandas as pd
from crypto_pandas import CCXTPandasExchange
from datetime import datetime, timedelta
from typing import Dict, Optional

class BreakoutStrategy:
    """4H/30min 突破策略"""
    
    def __init__(self, symbol: str = "BTC/USDT"):
        self.symbol = symbol
        self.exchange = CCXTPandasExchange(exchange=ccxt.binance())
        
        # 存储前高数据
        self.h4_high = None
        self.m30_high = None
        self.last_signal = None  # 避免重复推送
        
    def fetch_highs(self) -> Dict:
        """获取4H和30分钟周期的前高"""
        try:
            # 获取4小时K线（取最近100根找高点）
            ohlcv_h4 = self.exchange.fetch_ohlcv(
                self.symbol, 
                timeframe="4h", 
                limit=100
            )
            # 排除当前未完成的K线，用前一个完整K线的最高点
            prev_h4_high = ohlcv_h4.iloc[-2]['high'] if len(ohlcv_h4) >= 2 else None
            
            # 获取30分钟K线
            ohlcv_m30 = self.exchange.fetch_ohlcv(
                self.symbol,
                timeframe="30m",
                limit=100
            )
            prev_m30_high = ohlcv_m30.iloc[-2]['high'] if len(ohlcv_m30) >= 2 else None
            
            # 当前实时价格
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            
            return {
                'current_price': current_price,
                'h4_prev_high': prev_h4_high,
                'm30_prev_high': prev_m30_high,
                'timestamp': datetime.now()
            }
        except Exception as e:
            print(f"获取K线数据失败: {e}")
            return None
    
    def check_signal(self) -> Optional[Dict]:
        """检查是否有交易信号"""
        data = self.fetch_highs()
        if not data:
            return None
        
        current = data['current_price']
        h4_high = data['h4_prev_high']
        m30_high = data['m30_prev_high']
        
        signal = None
        
        # 做多信号：4H突破 + 30min突破
        if h4_high and m30_high:
            # 4H级别突破（收盘价逻辑，这里用当前价模拟）
            h4_broken = current > h4_high * 1.001  # 0.1%过滤假突破
            # 30min级别突破
            m30_broken = current > m30_high * 1.001
            
            if h4_broken and m30_broken:
                signal_type = "LONG"
                signal = {
                    "type": signal_type,
                    "price": current,
                    "h4_high": h4_high,
                    "m30_high": m30_high,
                    "message": f"🟢 **做多信号**\n\n"
                               f"• 4H前高: ${h4_high:,.2f} ✅已突破\n"
                               f"• 30min前高: ${m30_high:,.2f} ✅已突破\n"
                               f"• 当前价格: ${current:,.2f}"
                }
            
            # 做空信号：4H跌破前低 + 30min跌破前低
            # 获取前低（简化：用最低点逻辑）
            ohlcv_h4 = self.exchange.fetch_ohlcv(self.symbol, "4h", limit=100)
            ohlcv_m30 = self.exchange.fetch_ohlcv(self.symbol, "30m", limit=100)
            h4_low = ohlcv_h4.iloc[-2]['low'] if len(ohlcv_h4) >= 2 else None
            m30_low = ohlcv_m30.iloc[-2]['low'] if len(ohlcv_m30) >= 2 else None
            
            if h4_low and m30_low:
                h4_broken_down = current < h4_low * 0.999
                m30_broken_down = current < m30_low * 0.999
                
                if h4_broken_down and m30_broken_down:
                    signal_type = "SHORT"
                    signal = {
                        "type": signal_type,
                        "price": current,
                        "message": f"🔴 **做空信号**\n\n"
                                   f"• 4H前低: ${h4_low:,.2f} ✅已跌破\n"
                                   f"• 30min前低: ${m30_low:,.2f} ✅已跌破\n"
                                   f"• 当前价格: ${current:,.2f}"
                    }
        
        # 防重复推送：同一信号5分钟内不重复
        if signal:
            signal_key = f"{signal['type']}_{data['timestamp'].strftime('%Y%m%d%H')}"
            if self.last_signal != signal_key:
                self.last_signal = signal_key
                return signal
        
        return None