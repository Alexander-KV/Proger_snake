import type { CSSProperties } from 'react'
import type { MatchLobbyData, RoundState } from './socket'

export default function MatchRound({
  match,
  round,
  onBack,
}: {
  match: MatchLobbyData
  round: RoundState
  onBack: () => void
}) {
  const finished = match.status === 'finished'
  const winners = new Set(round.winner_ids)
  const winnerNames = round.snakes
    .filter((snake) => winners.has(snake.team_id))
    .map((snake) => snake.name)
  const entries = round.snakes.map((snake, color) => ({ snake, color }))
  if (finished) {
    entries.sort(
      (a, b) =>
        Number(winners.has(b.snake.team_id)) -
          Number(winners.has(a.snake.team_id)) ||
        (b.snake.eliminated_at ?? round.tick + 1) -
          (a.snake.eliminated_at ?? round.tick + 1) ||
        b.snake.score - a.snake.score,
    )
  }
  const seconds = Math.max(1, Math.ceil(round.countdown_seconds))
  return (
    <div className="match-lobby">
      <section
        className="match-field match-round-field"
        aria-labelledby="match-field-title"
      >
        <div className="match-field-caption">
          <h2 id="match-field-title">Игровое поле</h2>
          <span>
            {match.board_size} × {match.board_size}
          </span>
        </div>
        <div
          aria-hidden="true"
          className="match-board match-round-board"
          style={{ '--board-size': match.board_size } as CSSProperties}
        >
          {round.food && (
            <span
              className="match-food"
              style={{
                gridColumn: round.food[0] + 1,
                gridRow: round.food[1] + 1,
              }}
            />
          )}
          {entries.flatMap(({ snake, color }) =>
            snake.body.map(([x, y], index) => (
              <span
                key={`${snake.team_id}:${x}:${y}`}
                className={
                  index === 0 ? 'match-snake-head' : 'match-snake-cell'
                }
                data-snake={color}
                style={{ gridColumn: x + 1, gridRow: y + 1 }}
              />
            )),
          )}
        </div>
      </section>

      <section className="match-roster" aria-labelledby="match-round-title">
        <div className="match-roster-heading">
          <h2 id="match-round-title">
            {finished ? 'Итоги матча' : 'Ход матча'}
          </h2>
          {match.status !== 'countdown' && <span>Ход {round.tick}</span>}
        </div>
        <p role="status" className="match-muted">
          {match.status === 'countdown'
            ? `До старта: ${seconds} с`
            : finished
              ? `${winnerNames.length === 1 ? 'Победитель' : 'Ничья'} — ${winnerNames.join(', ')}`
              : 'Игра идёт'}
        </p>
        <ul className="match-team-list match-round-teams">
          {entries.map(({ snake, color }) => (
            <li key={snake.team_id}>
              <div>
                <span className="match-snake-swatch" data-snake={color} />
                <strong>{snake.name}</strong>
                <div className="match-muted">
                  {snake.strategy === 'food' ? 'Поиск еды' : 'Свободное поле'}
                </div>
              </div>
              <div className="match-round-score">
                <strong>Очки: {snake.score}</strong>
                <div className="match-muted">
                  {snake.eliminated_at !== null
                    ? `Выбыла на ходу ${snake.eliminated_at}`
                    : finished
                      ? 'Выжила'
                      : 'В игре'}
                </div>
              </div>
            </li>
          ))}
        </ul>
        {finished && (
          <button className="match-button" onClick={onBack}>
            К списку матчей
          </button>
        )}
      </section>
    </div>
  )
}
