export type SignalDirection = 'long' | 'short'
export type SignalResult = 'pending' | 'win' | 'loss' | 'expired'

export interface SignalVote {
  name: string   // indicator name e.g. "RSI"
  vote: number   // +1 / -1 / 0
  reason: string // human-readable reason
}

export interface TradeSignal {
  id: string
  pair: string
  direction: SignalDirection
  entry: number
  stop_loss: number
  take_profit: number
  confidence: number
  rr_ratio?: number | null
  timestamp: string
  expires_at?: string | null
  result: SignalResult
  close_price: number | null
  votes_json?: SignalVote[] | null
}
