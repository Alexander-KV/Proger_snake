import { useRef, useState, type FormEvent } from 'react'
import {
  MatchError,
  MatchSocket,
  requestId,
  type OrganizerRole,
} from './socket'

export default function CreateMatch({
  socket,
  online,
  onCreated,
  onCancel,
}: {
  socket: MatchSocket
  online: boolean
  onCreated: (id: number) => void
  onCancel: () => void
}) {
  const [capacity, setCapacity] = useState(2)
  const [boardSize, setBoardSize] = useState(24)
  const [role, setRole] = useState<OrganizerRole>('organizer_observer')
  const [error, setError] = useState<MatchError>()
  const [busy, setBusy] = useState(false)
  const key = useRef<string | undefined>(undefined)

  function optionsChanged() {
    key.current = undefined
    setError(undefined)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !online) return
    setBusy(true)
    setError(undefined)
    try {
      key.current ??= requestId()
      const result = await socket.send(
        'create_match',
        { capacity, board_size: boardSize, organizer_role: role },
        key.current,
      )
      onCreated(result.id)
    } catch (failure) {
      if (failure instanceof MatchError) setError(failure)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="match-form" onSubmit={submit}>
      <fieldset
        disabled={busy}
        className="match-settings"
        onChange={optionsChanged}
      >
        <label>
          <span>Количество команд</span>
          <select
            value={capacity}
            onChange={(event) => setCapacity(Number(event.target.value))}
          >
            {[2, 3, 4].map((count) => (
              <option key={count}>{count}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Размер поля</span>
          <select
            value={boardSize}
            onChange={(event) => setBoardSize(Number(event.target.value))}
          >
            {[16, 24, 32].map((size) => (
              <option key={size} value={size}>
                {size} × {size}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="match-roles">
          <legend>Роль создателя</legend>
          <label>
            <input
              type="radio"
              name="organizer-role"
              checked={role === 'organizer_observer'}
              onChange={() => setRole('organizer_observer')}
            />
            Организатор-наблюдатель
          </label>
          <label>
            <input
              type="radio"
              name="organizer-role"
              checked={role === 'organizer_player'}
              onChange={() => setRole('organizer_player')}
            />
            Организатор и игрок
          </label>
        </fieldset>
      </fieldset>
      {error && (
        <p role="alert" className="match-error">
          {error.message}
        </p>
      )}
      <div className="match-actions">
        {error?.matchId === undefined ? (
          <button
            className="match-button is-primary"
            disabled={busy || !online}
          >
            {busy ? 'Создаём…' : 'Создать'}
          </button>
        ) : (
          <button
            type="button"
            className="match-button is-primary"
            onClick={() => onCreated(error.matchId!)}
          >
            Открыть текущий матч
          </button>
        )}
        <button
          type="button"
          className="match-button"
          onClick={onCancel}
          disabled={busy}
        >
          Отмена
        </button>
      </div>
    </form>
  )
}
