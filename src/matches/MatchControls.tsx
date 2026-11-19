import { useState } from 'react'
import type { MatchLobbyData } from './socket'

export default function MatchControls({
  data,
  disabled,
  onStart,
  onCancelCountdown,
  onCancelMatch,
}: {
  data: MatchLobbyData
  disabled: boolean
  onStart: (seconds: number) => void
  onCancelCountdown: () => void
  onCancelMatch: () => void
}) {
  const [seconds, setSeconds] = useState('0')
  const enoughPlayers = data.participant_count >= data.minimum_players
  const validCountdown =
    seconds !== '' && /^\d+$/.test(seconds) && Number(seconds) <= 60

  return (
    <section className="match-controls" aria-labelledby="match-controls-title">
      <h3 id="match-controls-title">Управление матчем</h3>
      {data.status === 'waiting' && (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (!disabled && enoughPlayers && validCountdown)
              onStart(Number(seconds))
          }}
        >
          <label htmlFor="match-countdown-seconds">
            Отсчёт до старта, сек.
          </label>
          <input
            id="match-countdown-seconds"
            type="number"
            min={0}
            max={60}
            step={1}
            required
            value={seconds}
            onChange={(event) => setSeconds(event.target.value)}
            aria-describedby="match-start-hint"
          />
          <p id="match-start-hint" className="match-muted">
            {enoughPlayers
              ? '0 — начать сразу.'
              : `Для старта нужны минимум ${data.minimum_players} команды.`}
          </p>
          <button
            className="match-button is-primary"
            disabled={disabled || !enoughPlayers || !validCountdown}
          >
            Начать матч
          </button>
        </form>
      )}
      {data.status === 'countdown' && (
        <button
          className="match-button"
          disabled={disabled}
          onClick={onCancelCountdown}
        >
          Остановить отсчёт
        </button>
      )}
      <button
        className="match-link"
        disabled={disabled}
        onClick={onCancelMatch}
      >
        Отменить матч
      </button>
    </section>
  )
}
