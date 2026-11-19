import type { CSSProperties } from 'react'
import type { Cell } from '../matches/socket'
import type { Arena } from './api'

const colors = ['#377a44', '#265e9d', '#ae510b', '#784594']
const legend = {
  normal: 'Обычная еда',
  gold: 'Золотая еда',
  poison: 'Яд',
  obstacle: 'Препятствие',
  water: 'Вода',
  shield: 'Щит',
} as const

export function ArenaBoard({ arena }: { arena: Arena }) {
  function position([x, y]: Cell): CSSProperties {
    return {
      left: `${(x / arena.width) * 100}%`,
      top: `${(y / arena.height) * 100}%`,
    }
  }

  const objects = [
    ...arena.water.map((cell) => ({ cell, kind: 'water' })),
    ...arena.obstacles.map((cell) => ({ cell, kind: 'obstacle' })),
    ...arena.food,
    ...arena.poison.map((cell) => ({ cell, kind: 'poison' })),
    ...arena.powerups,
  ]

  return (
    <section className="algorithm-field" aria-label="Игровое поле">
      <div className="match-field-caption">
        <h2>Игровое поле</h2>
        <span>
          {arena.width} × {arena.height} · Такт {arena.tick}/{arena.tick_limit}
        </span>
      </div>
      <div
        aria-hidden="true"
        className="algorithm-board"
        style={
          { '--columns': arena.width, '--rows': arena.height } as CSSProperties
        }
      >
        {objects.map(({ cell, kind }) => (
          <span
            key={cell.join(',')}
            className={`arena-cell arena-${kind}`}
            style={position(cell)}
          />
        ))}
        {arena.snakes.map(
          (snake, index) =>
            snake.head && (
              <div
                key={snake.id}
                style={{ '--snake': colors[index] } as CSSProperties}
              >
                {snake.body
                  .slice(snake.movement?.progress ? 0 : 1)
                  .map((cell) => (
                    <span
                      key={cell.join(',')}
                      className="arena-cell arena-body"
                      style={position(cell)}
                    />
                  ))}
                <span
                  className={`arena-cell arena-head${snake.effects?.shield_ticks ? ' is-shielded' : ''}`}
                  style={position(snake.head)}
                />
              </div>
            ),
        )}
      </div>
      <ul className="arena-legend" aria-label="Обозначения поля">
        {Object.entries(legend).map(([kind, name]) => (
          <li key={kind}>
            <span aria-hidden="true" className={`arena-${kind}`} />
            {name}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function ArenaResults({
  arena,
  versionNames = {},
}: {
  arena: Arena
  versionNames?: Record<number, string>
}) {
  if (!arena.finished) {
    return (
      <ul className="match-team-list" aria-label="Очки участников">
        {arena.snakes.map((snake, index) => (
          <li key={snake.id}>
            <span>
              <span
                className="match-team-color"
                style={{ backgroundColor: colors[index] }}
              />
              {snake.name}
            </span>
            <span>
              {snake.score} очк. · {snake.length} кл.
              {!snake.alive
                ? ' · Погибла'
                : snake.effects?.shield_ticks
                  ? ` · Щит (${snake.effects.shield_ticks})`
                  : snake.movement?.slowed
                    ? ' · Замедлена'
                    : ''}
            </span>
          </li>
        ))}
      </ul>
    )
  }
  const winnerNames = arena.snakes
    .filter((snake) => arena.winners.includes(snake.id))
    .map((snake) => snake.name)
  return (
    <div className="match-table-wrap">
      <p className="match-result" role="status">
        {winnerNames.length === 0
          ? 'Победителя нет'
          : `${winnerNames.length > 1 ? 'Ничья' : 'Победитель'} · ${winnerNames.join(', ')}`}
      </p>
      {arena.results.length > 0 && (
        <table className="match-table" aria-label="Результаты матча">
          <thead>
            <tr>
              <th scope="col">Место</th>
              <th scope="col">Участник</th>
              <th scope="col">Очки</th>
              <th scope="col">Длина</th>
              <th scope="col">Статус</th>
            </tr>
          </thead>
          <tbody>
            {arena.results.map((row) => (
              <tr key={row.id}>
                <td>{row.place}</td>
                <th scope="row">
                  {row.name}
                  {versionNames[row.id] && (
                    <small className="arena-version">
                      {versionNames[row.id]}
                    </small>
                  )}
                </th>
                <td>{row.score}</td>
                <td>{row.length}</td>
                <td>{row.alive ? 'Выжила' : 'Погибла'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
