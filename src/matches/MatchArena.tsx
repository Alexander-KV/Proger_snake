import { useEffect, useState, type CSSProperties } from 'react'
import type { Cell, MatchLobbyData } from './socket'

const teamColors = ['#8ce65d', '#58b9ff', '#ff9f61', '#d8a8ff']

function position([x, y]: Cell): CSSProperties {
  return { gridColumn: x + 1, gridRow: y + 1 }
}

function Countdown({
  startsAt,
  serverTime,
}: {
  startsAt: number
  serverTime: number
}) {
  const [deadline] = useState(
    () => performance.now() + (startsAt - serverTime) * 1000,
  )
  const [seconds, setSeconds] = useState(() =>
    Math.max(0, Math.ceil(startsAt - serverTime)),
  )

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSeconds(Math.max(0, Math.ceil((deadline - performance.now()) / 1000)))
    }, 100)
    return () => window.clearInterval(timer)
  }, [deadline])

  return (
    <div className="match-countdown" role="status">
      {seconds > 0 ? `Старт через ${seconds} с` : 'Ожидаем старта…'}
    </div>
  )
}

export default function MatchArena({ data }: { data: MatchLobbyData }) {
  const game = data.game

  return (
    <section className="match-field" aria-labelledby="match-field-title">
      <div className="match-field-caption">
        <h2 id="match-field-title" tabIndex={-1}>
          {data.status === 'waiting' ? 'Размер поля' : 'Игровое поле'}
        </h2>
        <span>
          {data.board_size} × {data.board_size}
        </span>
      </div>
      <div className="match-arena">
        <div
          aria-hidden="true"
          className="match-board"
          style={{ '--board-size': data.board_size } as CSSProperties}
        >
          {game?.food && (
            <span className="match-food" style={position(game.food)} />
          )}
          {game?.snakes.flatMap((snake, index) =>
            snake.body.map((cell, segment) => (
              <span
                className={
                  segment === 0 ? 'match-snake-head' : 'match-snake-body'
                }
                key={`${snake.team_id}-${segment}`}
                style={{
                  ...position(cell),
                  backgroundColor: teamColors[index],
                }}
              />
            )),
          )}
        </div>
        {data.starts_at !== null && (
          <Countdown
            key={data.starts_at}
            startsAt={data.starts_at}
            serverTime={data.server_time}
          />
        )}
      </div>
    </section>
  )
}

export function MatchScores({
  game,
  finished,
  organizerId,
}: {
  game: NonNullable<MatchLobbyData['game']>
  finished: boolean
  organizerId: number
}) {
  const winnerNames = game.snakes
    .filter((snake) => game.winners.includes(snake.team_id))
    .map((snake) => snake.name)
    .join(', ')

  return (
    <>
      {finished && (
        <p className="match-result" role="status">
          {game.winners.length === 1 ? 'Победитель' : 'Победители'} ·{' '}
          {winnerNames}
        </p>
      )}
      <ul className="match-team-list" aria-label="Очки команд">
        {game.snakes.map((snake, index) => (
          <li key={snake.team_id}>
            <span>
              <span
                className="match-team-color"
                style={{ backgroundColor: teamColors[index] }}
              />
              {snake.name}
              {snake.team_id === organizerId && (
                <span className="match-muted"> · Организатор</span>
              )}
            </span>
            <span>
              {snake.score}
              {!snake.alive && ' · Выбыла'}
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}
