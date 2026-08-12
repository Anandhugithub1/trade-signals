export type SignalDirection = 'long' | 'short'
export type SignalResult = 'pending' | 'win' | 'loss' | 'expired'
// 'donchian' and 'mean_reversion' are the two live engines; 'legacy' is
// retired (its history was deleted from trade_signals) but the type stays
// permissive in case older cached data or a stray row still carries it.
export type SignalStrategy = 'donchian' | 'mean_reversion' | 'legacy' | string

export interface TradeSignal {
  id: string
  pair: string
  direction: SignalDirection
  entry: number
  stop_loss: number
  take_profit: number
  confidence: number
  strategy: SignalStrategy
  rr_ratio?: number | null
  latest_price?: number | null
  entry_confirmed?: boolean  // true once price has touched the limit entry
  timestamp: string
  expires_at?: string | null
  result: SignalResult
  close_price: number | null
  votes_json?: Record<string, number> | null  // compact: {"MACD hist":1,"EMA200":1,"Macro":-1}
  note?: string | null  // main reason for the trade, max 500 chars
}
