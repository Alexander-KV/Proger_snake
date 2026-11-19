import { useState } from 'react'
import { MatchError, MatchSocket } from './socket'
import useMatchSubscription from './useMatchSubscription'

export default function MatchList({
  socket,
  online,
  onOpen,
  onCreate,
}: {
  socket: MatchSocket
  online: boolean
  onOpen: (id: number) => void
  onCreate: () => void
}) {
  const { data, error, retry } = useMatchSubscription(socket, { view: 'list' })
  const [actionError, setActionError] = useState<MatchError>()
  const [joining, setJoining] = useState<number>()

  async function join(id: number) {
    setJoining(id)
    setActionError(undefined)
    try {
      const result = await socket.send('join_match', { match_id: id })
      onOpen(result.id)
    } catch (failure) {
      if (failure instanceof MatchError) {
        setActionError(failure)
        if (
          ['match_full', 'active_match', 'match_not_waiting'].includes(
            failure.code,
          )
        )
          retry()
      }
    } finally {
      setJoining(undefined)
    }
  }

  if (error)
    return (
      <>
        <p className="match-error" role="alert">
          {error.message}
        </p>
        <button className="match-button" onClick={retry} disabled={!online}>
          Повторить
        </button>
      </>
    )
  if (!data || !('matches' in data))
    return <p role="status">Загружаем матчи…</p>

  const currentMatch = data.current_match_id
  const hasCurrentMatch = currentMatch !== null
  return (
    <>
      {actionError && (
        <p className="match-error" role="alert">
          {actionError.message}
        </p>
      )}
      {hasCurrentMatch && (
        <p className="match-current">
          Ваша команда уже в матче.{' '}
          <button className="match-link" onClick={() => onOpen(currentMatch)}>
            Открыть текущий матч
          </button>
        </p>
      )}
      {data.matches.length === 0 ? (
        <div className="match-empty">
          <p>Пока нет матчей.</p>
          <button className="match-button is-primary" onClick={onCreate}>
            Создать матч
          </button>
        </div>
      ) : (
        <>
          {!hasCurrentMatch && (
            <div className="match-actions mb-4">
              <button className="match-button is-primary" onClick={onCreate}>
                Создать матч
              </button>
            </div>
          )}
          <div className="match-table-wrap">
            <table className="match-table" aria-label="Список матчей">
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Команды</th>
                  <th scope="col">Поле</th>
                  <th scope="col">Статус</th>
                  <th scope="col">Действие</th>
                </tr>
              </thead>
              <tbody>
                {data.matches.map((match) => {
                  const isCurrent = currentMatch === match.id
                  const full = match.participant_count >= match.capacity
                  const waiting = match.status === 'waiting'
                  return (
                    <tr key={match.id}>
                      <th scope="row">#{match.id}</th>
                      <td>
                        {match.participant_count} / {match.capacity}
                      </td>
                      <td>
                        {match.board_size} × {match.board_size}
                      </td>
                      <td>
                        {!waiting
                          ? match.status === 'countdown'
                            ? 'Отсчёт до старта'
                            : 'Идёт игра'
                          : full
                            ? 'Заполнен'
                            : 'Ожидает команды'}
                      </td>
                      <td>
                        {isCurrent ? (
                          <button
                            className="match-link"
                            onClick={() => onOpen(match.id)}
                          >
                            {waiting ? 'Открыть лобби' : 'Открыть матч'}
                          </button>
                        ) : waiting && !full && !hasCurrentMatch ? (
                          <button
                            className="match-link"
                            disabled={!online || joining !== undefined}
                            onClick={() => void join(match.id)}
                          >
                            {joining === match.id
                              ? 'Подключаемся…'
                              : 'Подключиться'}
                          </button>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  )
}
