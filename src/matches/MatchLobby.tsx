import { useRef, useState, type CSSProperties } from 'react'
import MatchGuide from './MatchGuide'
import { MatchError, MatchSocket } from './socket'
import useMatchSubscription from './useMatchSubscription'

export default function MatchLobby({
  socket,
  online,
  matchId,
  onBack,
}: {
  socket: MatchSocket
  online: boolean
  matchId: number
  onBack: () => void
}) {
  const { data, error, retry } = useMatchSubscription(socket, {
    view: 'lobby',
    match_id: matchId,
  })
  const [guide, setGuide] = useState<'rules' | 'docs'>()
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const dialog = useRef<HTMLDialogElement>(null)
  const guideButton = useRef<'rules' | 'docs'>('rules')
  const rulesButton = useRef<HTMLButtonElement>(null)
  const docsButton = useRef<HTMLButtonElement>(null)
  const guideHeading = useRef<HTMLDivElement>(null)

  function closeGuide() {
    setGuide(undefined)
    requestAnimationFrame(() => {
      ;(guideButton.current === 'rules'
        ? rulesButton
        : docsButton
      ).current?.focus()
    })
  }

  async function exit(close: boolean) {
    setBusy(true)
    setActionError('')
    try {
      await socket.send(close ? 'close_match' : 'leave_match', {
        match_id: matchId,
      })
      dialog.current?.close()
      onBack()
    } catch (error) {
      if (error instanceof MatchError) setActionError(error.message)
    } finally {
      setBusy(false)
    }
  }

  if (error)
    return (
      <>
        <p role="alert" className="match-error">
          {error.message}
        </p>
        <div className="match-actions">
          {error.code === 'unavailable' && (
            <button className="match-button" onClick={retry} disabled={!online}>
              Повторить
            </button>
          )}
          <button className="match-button" onClick={onBack}>
            ← К матчам
          </button>
        </div>
      </>
    )
  if (!data || !('participants' in data))
    return <p role="status">Загружаем состав…</p>
  if (guide)
    return (
      <div ref={guideHeading} tabIndex={-1}>
        <MatchGuide section={guide} onBack={closeGuide} />
      </div>
    )

  const isOrganizer = data.my_role !== 'participant'
  return (
    <div className="match-lobby">
      <section className="match-field" aria-labelledby="match-field-title">
        <div className="match-field-caption">
          <h2 id="match-field-title">Тренировочное поле</h2>
          <span>
            {data.board_size} × {data.board_size}
          </span>
        </div>
        <div
          aria-hidden="true"
          className="match-board"
          style={{ '--board-size': data.board_size } as CSSProperties}
        />
      </section>

      <section className="match-roster" aria-labelledby="match-roster-title">
        <div className="match-roster-heading">
          <h2 id="match-roster-title">Команды</h2>
          <span>
            {data.participant_count} / {data.capacity}
          </span>
        </div>
        <p className="match-muted">Организатор · {data.organizer.name}</p>
        {data.participants.length ? (
          <ul className="match-team-list">
            {data.participants.map((team) => (
              <li key={team.id}>
                <span>{team.name}</span>
                {data.organizer.id === team.id && (
                  <span className="match-muted">Организатор</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="match-empty-roster">Пока никто не присоединился.</p>
        )}
        <div className="match-resources">
          <h3>Перед началом</h3>
          <button
            ref={rulesButton}
            className="match-link"
            onClick={() => {
              guideButton.current = 'rules'
              setGuide('rules')
              requestAnimationFrame(() => guideHeading.current?.focus())
            }}
          >
            Правила игры
          </button>
          <button
            ref={docsButton}
            className="match-link"
            onClick={() => {
              guideButton.current = 'docs'
              setGuide('docs')
              requestAnimationFrame(() => guideHeading.current?.focus())
            }}
          >
            Документация
          </button>
        </div>
        {!isOrganizer && actionError && (
          <p className="match-error" role="alert">
            {actionError}
          </p>
        )}
        {isOrganizer ? (
          <button
            className="match-button"
            type="button"
            onClick={() => {
              setActionError('')
              dialog.current?.showModal()
            }}
            disabled={!online}
          >
            Закрыть лобби
          </button>
        ) : (
          <button
            className="match-button"
            type="button"
            disabled={busy || !online}
            onClick={() => void exit(false)}
          >
            {busy ? 'Выходим…' : 'Покинуть матч'}
          </button>
        )}
      </section>
      {isOrganizer && (
        <dialog
          ref={dialog}
          className="auth-dialog"
          aria-labelledby="close-lobby-title"
          onCancel={(event) => {
            if (busy) event.preventDefault()
          }}
        >
          <h2 id="close-lobby-title">Закрыть лобби?</h2>
          <p>Все команды смогут присоединиться к другому матчу.</p>
          {actionError && (
            <p className="match-error" role="alert">
              {actionError}
            </p>
          )}
          <div className="match-actions">
            <button
              className="match-button"
              disabled={busy || !online}
              onClick={() => void exit(true)}
            >
              {busy ? 'Закрываем…' : 'Закрыть'}
            </button>
            <button
              className="match-button is-primary"
              autoFocus
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Отмена
            </button>
          </div>
        </dialog>
      )}
    </div>
  )
}
