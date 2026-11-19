export type OrganizerRole = 'organizer_observer' | 'organizer_player'
export type MatchRole = OrganizerRole | 'participant'

type MatchStatus = 'waiting' | 'countdown' | 'running' | 'finished'

export type MatchSummary = {
  id: number
  capacity: number
  board_size: number
  participant_count: number
  status: MatchStatus
}

export type MatchListData = {
  current_match_id: number | null
  matches: MatchSummary[]
}

type TeamLabel = { id: number; name: string }

export type Cell = [number, number]

export type GameState = {
  tick: number
  food: Cell | null
  snakes: {
    team_id: number
    name: string
    body: Cell[]
    alive: boolean
    score: number
  }[]
  winners: number[]
}

export type MatchLobbyData = MatchSummary & {
  organizer: TeamLabel
  participants: TeamLabel[]
  my_role: MatchRole
  minimum_players: number
  starts_at: number | null
  server_time: number
  game: GameState | null
}

export type CreateMatchInput = {
  capacity: number
  board_size: number
  organizer_role: OrganizerRole
}

export type MatchView = { view: 'list' } | { view: 'lobby'; match_id: number }
export type Connection = 'connecting' | 'online' | 'offline'

export class MatchError extends Error {
  readonly code: string
  readonly matchId?: number

  constructor(message: string, code: string, matchId?: number) {
    super(message)
    this.code = code
    this.matchId = matchId
  }
}

export type MatchSnapshot = MatchListData | MatchLobbyData

type ServerMessage =
  | { type: 'result'; request_id: string; payload: { id: number } }
  | {
      type: 'error'
      request_id: string
      code: string
      message: string
      match_id?: number
    }
  | { type: 'snapshot'; subscription_id: string; payload: MatchSnapshot }
  | {
      type: 'subscription_end'
      subscription_id: string
      code: string
      message: string
    }

type Pending = {
  resolve: (value: { id: number }) => void
  reject: (error: MatchError) => void
  timer: number
}

type Subscription = {
  id?: string
  view: MatchView
  onSnapshot: (value: MatchSnapshot) => void
  onError: (error: MatchError) => void
}

export function requestId() {
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')
}

function connectionError() {
  return new MatchError(
    'Связь с сервером прервана. Попробуйте ещё раз.',
    'offline',
  )
}

export class MatchSocket {
  private socket: WebSocket | undefined
  private subscription: Subscription | undefined
  private pending = new Map<string, Pending>()
  private retryTimer = 0
  private retryDelay = 500
  private readonly onConnection: (state: Connection) => void
  private readonly onExpired: () => void

  constructor(
    onConnection: (state: Connection) => void,
    onExpired: () => void,
  ) {
    this.onConnection = onConnection
    this.onExpired = onExpired
  }

  open() {
    const url = new URL('/api/ws', window.location.href)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(url)
    this.socket = socket

    socket.onopen = () => {
      if (this.socket !== socket) return
      this.retryDelay = 500
      this.onConnection('online')
      if (this.subscription) this.activate(this.subscription)
    }

    socket.onmessage = (event: MessageEvent<string>) => {
      if (this.socket === socket)
        this.receive(JSON.parse(event.data) as ServerMessage)
    }

    socket.onclose = (event) => {
      if (this.socket !== socket) return
      this.failPending()
      if (event.code === 1008) {
        this.onExpired()
        return
      }

      this.onConnection('offline')
      this.retryTimer = window.setTimeout(() => this.open(), this.retryDelay)
      this.retryDelay = Math.min(8000, this.retryDelay * 2)
    }
  }

  reconnect() {
    if (this.socket?.readyState !== WebSocket.CLOSED) return
    window.clearTimeout(this.retryTimer)
    this.onConnection('connecting')
    this.open()
  }

  private receive(message: ServerMessage) {
    if (message.type === 'snapshot' || message.type === 'subscription_end') {
      const subscription = this.subscription
      if (subscription?.id !== message.subscription_id) return
      if (message.type === 'snapshot') subscription.onSnapshot(message.payload)
      else subscription.onError(new MatchError(message.message, message.code))
      return
    }

    const pending = this.pending.get(message.request_id)
    if (!pending) return
    window.clearTimeout(pending.timer)
    this.pending.delete(message.request_id)
    if (message.type === 'result') pending.resolve(message.payload)
    else
      pending.reject(
        new MatchError(message.message, message.code, message.match_id),
      )
  }

  private activate(subscription: Subscription) {
    const id = requestId()
    subscription.id = id
    void this.send('subscribe', subscription.view, id).catch(
      (error: MatchError) => {
        if (
          this.subscription === subscription &&
          subscription.id === id &&
          error.code !== 'offline'
        ) {
          subscription.onError(error)
        }
      },
    )
  }

  subscribe(
    view: MatchView,
    onSnapshot: Subscription['onSnapshot'],
    onError: Subscription['onError'],
  ) {
    const subscription = { view, onSnapshot, onError }
    this.subscription = subscription
    if (this.socket?.readyState === WebSocket.OPEN) this.activate(subscription)
    return () => {
      if (this.subscription !== subscription) return
      this.subscription = undefined
      if (this.socket?.readyState === WebSocket.OPEN) {
        void this.send('unsubscribe', {}).catch(() => undefined)
      }
    }
  }

  send(
    type: string,
    payload: object,
    key = requestId(),
  ): Promise<{ id: number }> {
    const socket = this.socket
    if (!socket || socket.readyState !== WebSocket.OPEN)
      return Promise.reject(connectionError())

    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => socket.close(), 12_000)
      this.pending.set(key, { resolve, reject, timer })
      try {
        socket.send(JSON.stringify({ type, request_id: key, payload }))
      } catch {
        window.clearTimeout(timer)
        this.pending.delete(key)
        reject(connectionError())
      }
    })
  }

  private failPending() {
    for (const pending of this.pending.values()) {
      window.clearTimeout(pending.timer)
      pending.reject(connectionError())
    }
    this.pending.clear()
  }

  close() {
    window.clearTimeout(this.retryTimer)
    const socket = this.socket
    this.socket = undefined
    socket?.close()
    this.failPending()
    this.retryDelay = 500
  }
}
