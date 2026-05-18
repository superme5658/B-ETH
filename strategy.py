import ccxt
import pandas as pd
from datetime import datetime
from typing import Dict, Optional


class BreakoutStrategy:
    """4H/30min 突破策略 - 使用 OKX 数据"""
    
    def __init__(self, symbol: str = "BTC"):
        self.symbol = f"{symbol}/USDT"
        # 使用 OKX 交易所
        self.exchange = ccxt.okx({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',  # 现货交易
            }
        })
        
        # 存储前高前低数据
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
            return None, None, None, None
        
        # 使用前一根完整K线（排除当前未完成的）
        prev_candle = df.iloc[-2]
        return prev_candle['high'], prev_candle['low'], prev_candle['open'], prev_candle['close']
    
    def check_signal(self, current_price: float) -> Optional[Dict]:
        """检查是否有交易信号"""
        # 获取4H周期数据
        h4_high, h4_low, h4_open, h4_close = self.get_prev_period_high_low('4h')
        
        # 获取30分钟周期数据（OKX支持30m周期）
        m30_high, m30_low, m30_open, m30_close = self.get_prev_period_high_low('30m')
        
        if not h4_high or not m30_high or not h4_low or not m30_low:
            print("无法获取K线数据，稍后重试...")
            return None
        
        signal = None
        
        # 做多信号：4H突破前高 + 30min突破前高
        # 使用0.2%的过滤阈值避免假突破
        h4_broken = current_price > h4_high * 1.002
        m30_broken = current_price > m30_high * 1.002
        
        if h4_broken and m30_broken:
            # 检查是否重复推送（每小时最多一次）
            current_hour = datetime.now().strftime('%Y%m%d%H')
            signal_key = f"LONG_{current_hour}"
            
            if self.last_signal_time != signal_key:
                self.last_signal_time = signal_key
                signal = {
                    "type": "LONG",
                    "price": current_price,
                    "h4_high": h4_high,
                    "m30_high": m30_high,
                    "message": f"🟢 **做多信号 (LONG)**\n\n"
                               f"━━━━━━━━━━━━━━━━━━━\n"
                               f"📈 **4H 周期**\n"
                               f"  • 前高: ${h4_high:,.2f}\n"
                               f"  • 状态: ✅ 已突破\n\n"
                               f"⏰ **30min 周期**\n"
                               f"  • 前高: ${m30_high:,.2f}\n"
                               f"  • 状态: ✅ 已突破\n\n"
                               f"💰 **当前价格**: ${current_price:,.2f}\n"
                               f"━━━━━━━━━━━━━━━━━━━\n\n"
                               f"**📌 操作建议**\n"
                               f"• 入场: 回踩 ${m30_high:,.2f} 附近\n"
                               f"• 止损: 4H前低 ${h4_low:,.2f} 下方\n"
                               f"• 止盈: 前高 + 5% ~ 10%"
                }
        
        # 做空信号：4H跌破前低 + 30min跌破前低
        h4_broken_down = current_price < h4_low * 0.998
        m30_broken_down = current_price < m30_low * 0.998
        
        if h4_broken_down and m30_broken_down:
            current_hour = datetime.now().strftime('%Y%m%d%H')
            signal_key = f"SHORT_{current_hour}"
            
            if self.last_signal_time != signal_key:
                self.last_signal_time = signal_key
                signal = {
                    "type": "SHORT",
                    "price": current_price,
                    "message": f"🔴 **做空信号 (SHORT)**\n\n"
                               f"━━━━━━━━━━━━━━━━━━━\n"
                               f"📉 **4H 周期**\n"
                               f"  • 前低: ${h4_low:,.2f}\n"
                               f"  • 状态: ✅ 已跌破\n\n"
                               f"⏰ **30min 周期**\n"
                               f"  • 前低: ${m30_low:,.2f}\n"
                               f"  • 状态: ✅ 已跌破\n\n"
                               f"💰 **当前价格**: ${current_price:,.2f}\n"
                               f"━━━━━━━━━━━━━━━━━━━\n\n"
                               f"**📌 操作建议**\n"
                               f"• 入场: 反弹 ${m30_low:,.2f} 附近\n"
                               f"• 止损: 4H前高 ${h4_high:,.2f} 上方\n"
                               f"• 止盈: 前低 - 5% ~ 10%"
                }
        
        return signal
