import ccxt
import pandas as pd
from datetime import datetime
from typing import Dict, Optional


class BreakoutStrategy:
    """4H/30min 突破策略 - 优化版"""
    
    def __init__(self, symbol: str):
        self.symbol = f"{symbol}/USDT"
        self.symbol_name = symbol
        self.exchange = ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'},
        })
        
        # 信号去重缓存（记录上次推送的K线收盘时间）
        self.last_signal_key = None
        
        # 信号确认计数（连续N次检查都满足才推送）
        self.confirmation_count = {side: 0 for side in ['long', 'short']}
        self.required_confirmations = 2  # 需要连续2次检查确认
        
    def fetch_ohlcv_data(self, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """获取K线数据，带缓存"""
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
            print(f"[{self.symbol_name}] 获取{timeframe}K线失败: {e}")
            return pd.DataFrame()
    
    def get_prev_period_high_low(self, timeframe: str) -> tuple:
        """获取前一个完整周期的最高点和最低点"""
        df = self.fetch_ohlcv_data(timeframe)
        if df.empty or len(df) < 2:
            return None, None
        
        prev_candle = df.iloc[-2]
        return prev_candle['high'], prev_candle['low']
    
    def get_current_period_key(self) -> str:
        """获取当前4H周期的唯一标识（用于去重）"""
        now = datetime.now()
        # 4小时周期：每4小时一个周期，如 0-4, 4-8, 8-12, 12-16, 16-20, 20-24
        period_4h = (now.hour // 4) * 4
        return f"{now.year}{now.month:02d}{now.day:02d}_{period_4h:02d}"
    
    def check_signal(self, current_price: float) -> Optional[Dict]:
        """检查是否有交易信号（带确认机制）"""
        h4_high, h4_low = self.get_prev_period_high_low('4h')
        m30_high, m30_low = self.get_prev_period_high_low('30m')
        
        if not all([h4_high, h4_low, m30_high, m30_low]):
            return None
        
        # 阈值设置（可用环境变量调整）
        threshold_pct = 0.002  # 0.2%
        h4_break_high = current_price > h4_high * (1 + threshold_pct)
        m30_break_high = current_price > m30_high * (1 + threshold_pct)
        h4_break_low = current_price < h4_low * (1 - threshold_pct)
        m30_break_low = current_price < m30_low * (1 - threshold_pct)
        
        current_period_key = self.get_current_period_key()
        signal = None
        
        # 做多信号确认逻辑
        if h4_break_high and m30_break_high:
            self.confirmation_count['long'] += 1
            self.confirmation_count['short'] = 0  # 重置相反方向计数
            
            if (self.confirmation_count['long'] >= self.required_confirmations and 
                self.last_signal_key != f"LONG_{current_period_key}"):
                
                self.last_signal_key = f"LONG_{current_period_key}"
                signal = {
                    "type": "LONG",
                    "symbol": self.symbol_name,
                    "price": current_price,
                    "h4_high": h4_high,
                    "m30_high": m30_high,
                    "h4_low": h4_low,
                    "confidence": self.confirmation_count['long'],
                    "message": self._build_long_message(current_price, h4_high, m30_high, h4_low)
                }
        else:
            self.confirmation_count['long'] = 0
        
        # 做空信号确认逻辑
        if h4_break_low and m30_break_low:
            self.confirmation_count['short'] += 1
            self.confirmation_count['long'] = 0
            
            if (self.confirmation_count['short'] >= self.required_confirmations and 
                self.last_signal_key != f"SHORT_{current_period_key}"):
                
                self.last_signal_key = f"SHORT_{current_period_key}"
                signal = {
                    "type": "SHORT",
                    "symbol": self.symbol_name,
                    "price": current_price,
                    "confidence": self.confirmation_count['short'],
                    "message": self._build_short_message(current_price, h4_high, h4_low, m30_low)
                }
        else:
            self.confirmation_count['short'] = 0
        
        return signal
    
    def _build_long_message(self, price: float, h4_high: float, m30_high: float, h4_low: float) -> str:
        return (
            f"🟢 **做多信号 (LONG)** - {self.symbol_name}/USDT\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📈 **4H 周期**\n"
            f"  • 前高: ${h4_high:,.2f}\n"
            f"  • 状态: ✅ 已突破\n\n"
            f"⏰ **30min 周期**\n"
            f"  • 前高: ${m30_high:,.2f}\n"
            f"  • 状态: ✅ 已突破\n\n"
            f"💰 **当前价格**: ${price:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"**📌 操作建议**\n"
            f"• 入场: 回踩 ${m30_high:,.2f} 附近\n"
            f"• 止损: 4H前低 ${h4_low:,.2f} 下方\n"
            f"• 止盈: 前高 + 5% ~ 10%\n"
            f"• 确认次数: {self.confirmation_count['long']}/2"
        )
    
    def _build_short_message(self, price: float, h4_high: float, h4_low: float, m30_low: float) -> str:
        return (
            f"🔴 **做空信号 (SHORT)** - {self.symbol_name}/USDT\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📉 **4H 周期**\n"
            f"  • 前低: ${h4_low:,.2f}\n"
            f"  • 状态: ✅ 已跌破\n\n"
            f"⏰ **30min 周期**\n"
            f"  • 前低: ${m30_low:,.2f}\n"
            f"  • 状态: ✅ 已跌破\n\n"
            f"💰 **当前价格**: ${price:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"**📌 操作建议**\n"
            f"• 入场: 反弹 ${m30_low:,.2f} 附近\n"
            f"• 止损: 4H前高 ${h4_high:,.2f} 上方\n"
            f"• 止盈: 前低 - 5% ~ 10%\n"
            f"• 确认次数: {self.confirmation_count['short']}/2"
        )
