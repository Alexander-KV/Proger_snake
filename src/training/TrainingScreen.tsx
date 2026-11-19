import { useCallback, useEffect, useRef, useState } from 'react'
import { ArenaBoard, ArenaResults } from './ArenaBoard'
import {
  botNames,
  defaultConfig,
  trainingRequest,
  type Bot,
  type Config,
  type MapOption,
  type PreparedMap,
  type Run,
} from './api'

const settings: {
  key: keyof Config
  label: string
  min: number
  max: number
}[] = [
  { key: 'width', label: 'Ширина', min: 8, max: 32 },
  { key: 'height', label: 'Высота', min: 8, max: 32 },
  { key: 'snake_count', label: 'Змейки', min: 2, max: 4 },
  { key: 'tick_limit', label: 'Лимит тактов', min: 1, max: 1000 },
  { key: 'obstacles', label: 'Препятствия', min: 0, max: 1024 },
  { key: 'water', label: 'Вода', min: 0, max: 1024 },
  { key: 'normal', label: 'Обычная еда', min: 0, max: 1024 },
  { key: 'gold', label: 'Золотая еда', min: 0, max: 1024 },
  { key: 'poison', label: 'Яд', min: 0, max: 1024 },
  { key: 'shields', label: 'Щиты', min: 0, max: 1024 },
]

const initialBots: Bot[] = ['hunter', 'pathfinding', 'survival']

function deleteRun(id: string) {
  return trainingRequest<void>(`/runs/${id}`, { method: 'DELETE' })
}

function describe(error: unknown) {
  return error instanceof Error
    ? error.message
    : 'Не удалось выполнить действие.'
}

export default function TrainingScreen({ source }: { source: string }) {
  const [map, setMap] = useState<PreparedMap>()
  const [config, setConfig] = useState(defaultConfig)
  const [bots, setBots] = useState(initialBots)
  const [maps, setMaps] = useState<MapOption[]>([])
  const [mapId, setMapId] = useState('')
  const [name, setName] = useState('')
  const [run, setRun] = useState<Run>()
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const active = useRef(false)
  const current = useRef<string>(undefined)
  const pending = useRef(false)

  useEffect(() => {
    active.current = true
    let disposed = false
    void Promise.allSettled([
      trainingRequest<PreparedMap>('/maps/generate', {
        method: 'POST',
        body: {},
      }),
      trainingRequest<MapOption[]>('/maps'),
    ]).then(([generated, saved]) => {
      if (disposed) return
      if (generated.status === 'fulfilled') {
        setMap(generated.value)
      } else {
        setError(describe(generated.reason))
      }
      if (saved.status === 'fulfilled') setMaps(saved.value)
    })
    return () => {
      disposed = true
      active.current = false
      if (current.current) {
        void deleteRun(current.current).catch(() => undefined)
        current.current = undefined
      }
    }
  }, [])

  const perform = useCallback(async (operation: () => Promise<void>) => {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await operation()
    } catch (failure) {
      if (active.current) setError(describe(failure))
    } finally {
      pending.current = false
      if (active.current) setBusy(false)
    }
  }, [])

  const step = useCallback(
    (snapshot: Run) =>
      perform(async () => {
        const path = `/runs/${snapshot.id}`
        let next: Run
        try {
          next = await trainingRequest<Run>(path + '/step', {
            method: 'POST',
            body: { expected_tick: snapshot.arena.tick },
            acceptConflict: true,
          })
        } catch (failure) {
          setPlaying(false)
          const recovered = await trainingRequest<Run>(path).catch(
            () => undefined,
          )
          if (current.current === snapshot.id && recovered) setRun(recovered)
          throw failure
        }
        if (current.current === snapshot.id) {
          setRun(next)
          if (next.arena.finished) setPlaying(false)
        }
      }),
    [perform],
  )

  useEffect(() => {
    if (!playing || !run || run.arena.finished || busy) return
    const timer = window.setTimeout(() => void step(run), 320 / speed)
    return () => window.clearTimeout(timer)
  }, [playing, run, busy, speed, step])

  const changed =
    !!map && settings.some(({ key }) => map.draft.config[key] !== config[key])
  const valid = settings.every(
    ({ key, min, max }) =>
      Number.isInteger(config[key]) && config[key] >= min && config[key] <= max,
  )
  const selectedBots = bots.slice(0, config.snake_count - 1)

  function prepare(kind: 'generate' | 'clear') {
    void perform(async () => {
      const result = await trainingRequest<PreparedMap>(`/maps/${kind}`, {
        method: 'POST',
        body:
          kind === 'clear' && map
            ? { config, seed: map.draft.seed }
            : { config },
      })
      if (!active.current) return
      setMap(result)
      setNotice(kind === 'clear' ? 'Поле очищено.' : 'Карта готова.')
    })
  }

  function save() {
    if (!map || !name.trim()) return
    void perform(async () => {
      const result = await trainingRequest<PreparedMap>('/maps', {
        method: 'POST',
        body: { name, draft: map.draft, bots: selectedBots },
      })
      if (
        !active.current ||
        result.id === undefined ||
        result.name === undefined
      )
        return
      setMap(result)
      setMapId(String(result.id))
      setMaps((all) => [{ id: result.id!, name: result.name! }, ...all])
      setNotice('Карта сохранена.')
    })
  }

  function load() {
    if (!mapId) return
    void perform(async () => {
      const result = await trainingRequest<PreparedMap>(`/maps/${mapId}`)
      if (!active.current) return
      setMap(result)
      setConfig(result.draft.config)
      setName(result.name ?? '')
      setBots([...(result.bots ?? []), ...initialBots].slice(0, 3))
      setNotice('Карта загружена.')
    })
  }

  function start() {
    if (!map) return
    setPlaying(false)
    void perform(async () => {
      const next = await trainingRequest<Run>('/runs', {
        method: 'POST',
        body: {
          source,
          ...(map.id === undefined ? { draft: map.draft } : { map_id: map.id }),
          bots: selectedBots,
          replace_run: current.current,
        },
      })
      if (!active.current) {
        void deleteRun(next.id).catch(() => undefined)
        return
      }
      current.current = next.id
      setRun(next)
      setPlaying(true)
    })
  }

  function stop() {
    const id = current.current
    setPlaying(false)
    if (!id) return
    void perform(async () => {
      await deleteRun(id)
      current.current = undefined
      setRun(undefined)
    })
  }

  const arena = run?.arena ?? map?.arena
  const status = run?.arena.finished
    ? 'Матч завершён'
    : playing
      ? 'Идёт тестовый матч'
      : run
        ? busy
          ? 'Завершается такт…'
          : 'Пауза'
        : 'Подготовка поля'

  return (
    <section className="algorithm-training" aria-labelledby="training-title">
      <div className="training-heading">
        <h3 id="training-title">Тестовый матч</h3>
        <span role="status">{status}</span>
      </div>
      {arena && <ArenaBoard arena={arena} />}
      {run && <ArenaResults arena={run.arena} />}
      {run?.error && (
        <p className="match-error" role="alert">
          Решение на такте {run.error.tick}
          {run.error.line ? ` · строка ${run.error.line}` : ''} ·{' '}
          {run.error.message}
        </p>
      )}
      {error && (
        <p className="match-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="match-muted" role="status">
          {notice}
        </p>
      )}
      <div className="match-actions">
        {run ? (
          <>
            {!run.arena.finished && (
              <>
                {playing ? (
                  <button
                    className="match-button"
                    onClick={() => setPlaying(false)}
                  >
                    Пауза
                  </button>
                ) : (
                  <button
                    className="match-button is-primary"
                    disabled={busy}
                    onClick={() => {
                      setError('')
                      setPlaying(true)
                    }}
                  >
                    Продолжить
                  </button>
                )}
                <button
                  className="match-button"
                  disabled={busy || playing}
                  onClick={() => void step(run)}
                >
                  Один такт
                </button>
              </>
            )}
            <button className="match-button" disabled={busy} onClick={start}>
              Перезапустить на этой карте
            </button>
            <button className="match-link" disabled={busy} onClick={stop}>
              {run.arena.finished ? 'К настройкам' : 'Завершить тест'}
            </button>
          </>
        ) : (
          <button
            className="match-button is-primary"
            disabled={!map || busy || changed || !source.trim()}
            onClick={start}
          >
            Запустить тест
          </button>
        )}
        <label className="arena-speed">
          Скорость
          <select
            value={speed}
            onChange={(event) => setSpeed(Number(event.target.value))}
          >
            {[0.5, 1, 2, 4].map((item) => (
              <option value={item} key={item}>
                {item}×
              </option>
            ))}
          </select>
        </label>
      </div>
      {!run && (
        <details open className="algorithm-help">
          <summary>Карта и соперники</summary>
          <fieldset disabled={busy}>
            <legend className="sr-only">Настройки карты</legend>
            <div className="training-settings">
              {settings.map(({ key, label, min, max }) => (
                <label key={key}>
                  {label}
                  <input
                    type="number"
                    min={min}
                    max={max}
                    step={1}
                    value={Number.isNaN(config[key]) ? '' : config[key]}
                    onChange={(event) =>
                      setConfig({
                        ...config,
                        [key]: event.target.valueAsNumber,
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <p className="match-muted">Укажите 0, чтобы отключить объект.</p>
            {changed && (
              <p className="match-muted">
                Сгенерируйте или очистите карту, чтобы применить настройки.
              </p>
            )}
            <div className="match-actions">
              <button
                className="match-button"
                disabled={!valid}
                onClick={() => prepare('generate')}
              >
                Сгенерировать
              </button>
              <button
                className="match-button"
                disabled={!valid}
                onClick={() => prepare('clear')}
              >
                Очистить поле
              </button>
              <button
                className="match-button"
                disabled={!map || !valid}
                onClick={() => prepare('generate')}
              >
                Перегенерировать
              </button>
            </div>
            <div className="training-settings">
              {selectedBots.map((bot, index) => (
                <label key={index}>
                  Соперник {index + 1}
                  <select
                    value={bot}
                    onChange={(event) =>
                      setBots((previous) =>
                        previous.map((item, slot) =>
                          slot === index ? (event.target.value as Bot) : item,
                        ),
                      )
                    }
                  >
                    {(Object.keys(botNames) as Bot[]).map((kind) => (
                      <option key={kind} value={kind}>
                        {botNames[kind]}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <div className="training-map-actions">
              <label>
                Название карты
                <input
                  value={name}
                  maxLength={80}
                  onChange={(event) => setName(event.target.value)}
                />
              </label>
              <button
                className="match-button"
                disabled={!map || changed || !name.trim()}
                onClick={save}
              >
                Сохранить карту
              </button>
              <label>
                Сохранённые карты
                <select
                  value={mapId}
                  onChange={(event) => setMapId(event.target.value)}
                >
                  <option value="">Выберите карту</option>
                  {maps.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </label>
              <button className="match-button" disabled={!mapId} onClick={load}>
                Загрузить
              </button>
            </div>
          </fieldset>
        </details>
      )}
    </section>
  )
}
