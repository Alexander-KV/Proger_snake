import { useRef, useState } from 'react'
import MatchArena, { MatchScores } from './MatchArena'
import MatchControls from './MatchControls'
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
  const returnButton = useRef<HTMLButtonElement>(null)
  const guideButton = useRef<'rules' | 'docs'>('rules')
  const rulesButton = useRef<HTMLButtonElement>(null)
  const docsButton = useRef<HTMLButtonElement>(null)
  const guideHeading = useRef<HTMLDivElement>(null)

  function closeGuide() {
    setGuide(undefined)
    requestAnimationFrame(() => {
      const button = (
        guideButton.current === 'rules' ? rulesButton : docsButton
      ).current
      if (button) button.focus()
      else document.getElementById('match-field-title')?.focus()
    })
  }

  async function act(
    action: 'close_match' | 'leave_match' | 'start_match' | 'cancel_countdown',
    payload: object = {},
  ) {
    setBusy(true)
    setActionError('')
    try {
      await socket.send(action, { match_id: matchId, ...payload })
      if (action === 'close_match' || action === 'leave_match') {
        dialog.current?.close()
        onBack()
      }
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
  if (guide && data.status !== 'waiting') setGuide(undefined)
  if (guide && data.status === 'waiting')
    return (
      <div ref={guideHeading} tabIndex={-1}>
        <MatchGuide section={guide} onBack={closeGuide} />
      </div>
    )

  const isOrganizer = data.my_role !== 'participant'
  const finished = data.status === 'finished'
  const waiting = data.status === 'waiting'
  return (
    <div className="match-lobby">
      <MatchArena data={data} />

      <section className="match-roster" aria-labelledby="match-roster-title">
        <div className="match-roster-heading">
          <h2 id="match-roster-title">Команды</h2>
          <span>
            {data.participant_count} / {data.capacity}
          </span>
        </div>
        <p className="match-muted">Организатор · {data.organizer.name}</p>
        {data.game ? (
          <MatchScores
            game={data.game}
            finished={finished}
            organizerId={data.organizer.id}
          />
        ) : data.participants.length ? (
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
        {waiting && (
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
        )}
        {actionError && (
          <p className="match-error" role="alert">
            {actionError}
          </p>
        )}
        {isOrganizer && !finished && (
          <MatchControls
            data={data}
            disabled={busy || !online}
            onStart={(seconds) =>
              void act('start_match', { countdown_seconds: seconds })
            }
            onCancelCountdown={() => void act('cancel_countdown')}
            onCancelMatch={() => {
              setActionError('')
              dialog.current?.showModal()
              returnButton.current?.focus()
            }}
          />
        )}
        {!isOrganizer && waiting && (
          <button
            className="match-button"
            type="button"
            disabled={busy || !online}
            onClick={() => void act('leave_match')}
          >
            {busy ? 'Выходим…' : 'Покинуть матч'}
          </button>
        )}
        {finished && (
          <button className="match-button" onClick={onBack}>
            К матчам
          </button>
        )}
      </section>
      {isOrganizer && !finished && (
        <dialog
          ref={dialog}
          className="auth-dialog"
          aria-labelledby="cancel-match-title"
          onCancel={(event) => {
            if (busy) event.preventDefault()
          }}
        >
          <h2 id="cancel-match-title">Отменить матч?</h2>
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
              onClick={() => void act('close_match')}
            >
              {busy ? 'Отменяем…' : 'Отменить матч'}
            </button>
            <button
              className="match-button is-primary"
              ref={returnButton}
              disabled={busy}
              onClick={() => dialog.current?.close()}
            >
              Вернуться
            </button>
          </div>
        </dialog>
      )}
    </div>
  )
}
