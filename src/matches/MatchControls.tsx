import { useState } from 'react'
import type { MatchLobbyData } from './socket'

export default function MatchControls({
  data,
  disabled,
  onStart,
  onCancelCountdown,
  onCancelPreparation,
  onCancelMatch,
}: {
  data: MatchLobbyData
  disabled: boolean
  onStart: (minutes: number) => void
  onCancelCountdown: () => void
  onCancelPreparation: () => void
  onCancelMatch: () => void
}) {
  const [minutes, setMinutes] = useState('10')
  const enoughPlayers = data.participant_count >= data.minimum_players
  const validDuration =
    /^\d+$/.test(minutes) && Number(minutes) >= 1 && Number(minutes) <= 120

  return (
    <section className="match-controls" aria-labelledby="match-controls-title">
      <h3 id="match-controls-title">Управление матчем</h3>
      {data.status === 'waiting' && (
        <form
          onSubmit={(event) => {
            event.preventDefault()
            if (!disabled && enoughPlayers && validDuration)
              onStart(Number(minutes))
          }}
        >
          <label htmlFor="match-preparation-minutes">
            Время на написание, мин.
          </label>
          <input
            id="match-preparation-minutes"
            type="number"
            min={1}
            max={120}
            step={1}
            required
            value={minutes}
            onChange={(event) => setMinutes(event.target.value)}
            aria-describedby="match-start-hint"
          />
          <p id="match-start-hint" className="match-muted">
            {enoughPlayers
              ? 'После подготовки матч начнётся автоматически.'
              : `Для старта нужны минимум ${data.minimum_players} команды.`}
          </p>
          <button
            className="match-button is-primary"
            disabled={disabled || !enoughPlayers || !validDuration}
          >
            Начать подготовку
          </button>
        </form>
      )}
      {data.status === 'preparing' && (
        <button
          className="match-button"
          disabled={disabled}
          onClick={onCancelPreparation}
        >
          Остановить подготовку
        </button>
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
