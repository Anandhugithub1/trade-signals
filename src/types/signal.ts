export type SignalDirection = 'long' | 'short'
export type SignalResult = 'pending' | 'win' | 'loss' | 'expired'

export interface TradeSignal {
  id: string
  pair: string
  direction: SignalDirection
  entry: number
  stop_loss: number
  take_profit: number
  confidence: number
  rr_ratio?: number | null
  latest_price?: number | null
  timestamp: string
  expires_at?: string | null
  result: SignalResult
  close_price: number | null
  votes_json?: Record<string, number> | null  // compact: {"MACD hist":1,"EMA200":1,"Macro":-1}
  note?: string | null  // main reason for the trade, max 500 chars
}
