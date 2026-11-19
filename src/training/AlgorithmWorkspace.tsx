import { EditorView } from '@codemirror/view'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  requestId,
  type AlgorithmVersion,
  type MatchLobbyData,
  type MatchSocket,
} from '../matches/socket'
import { AlgorithmEditor, template } from './AlgorithmEditor'
import AlgorithmHelp from './AlgorithmHelp'
import { trainingRequest, type Validation } from './api'
import TrainingScreen from './TrainingScreen'

const timeFormat = new Intl.DateTimeFormat('ru-RU', {
  dateStyle: 'short',
  timeStyle: 'short',
})

function VersionRow({
  version,
  disabled,
  onOpen,
  onSelect,
  onRename,
  implicit,
}: {
  version: AlgorithmVersion
  disabled: boolean
  onOpen: () => void
  onSelect: () => void
  onRename: (name: string) => Promise<boolean>
  implicit: boolean
}) {
  const [edit, setEdit] = useState<string>()
  async function rename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (edit?.trim() && (await onRename(edit))) setEdit(undefined)
  }
  return (
    <li className="algorithm-version">
      <div>
        <strong>{version.name}</strong>
        <time dateTime={new Date(version.submitted_at * 1000).toISOString()}>
          {timeFormat.format(version.submitted_at * 1000)}
        </time>
        {version.selected && (
          <span className="algorithm-selected">Выбрана для матча</span>
        )}
        {implicit && (
          <span className="match-muted">Используется по умолчанию</span>
        )}
      </div>
      {edit !== undefined ? (
        <form
          onSubmit={(event) => void rename(event)}
          className="algorithm-rename"
        >
          <label>
            Имя версии{' '}
            <input
              value={edit}
              maxLength={80}
              required
              onChange={(event) => setEdit(event.target.value)}
            />
          </label>
          <button className="match-button" disabled={disabled || !edit.trim()}>
            Сохранить имя
          </button>
          <button
            type="button"
            className="match-link"
            onClick={() => setEdit(undefined)}
          >
            Отмена
          </button>
        </form>
      ) : (
        <div className="match-actions">
          <button className="match-link" onClick={onOpen}>
            Открыть код
          </button>
          <button
            className="match-link"
            disabled={disabled}
            onClick={() => setEdit(version.name)}
          >
            Переименовать
          </button>
          <button
            className="match-link"
            disabled={disabled || version.selected}
            onClick={onSelect}
          >
            Выбрать для матча
          </button>
        </div>
      )}
    </li>
  )
}

export default function AlgorithmWorkspace({
  data,
  socket,
  online,
}: {
  data: MatchLobbyData
  socket: MatchSocket
  online: boolean
}) {
  const key = `snake-arena-draft-${data.my_team_id}-${data.id}`
  const [source, setSource] = useState(() => {
    try {
      return localStorage.getItem(key) ?? template
    } catch {
      return template
    }
  })
  const [training, setTraining] = useState(false)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)
  const [actionError, setActionError] = useState('')
  const [notice, setNotice] = useState('')
  const [checked, setChecked] = useState<{
    source: string
    result: Validation
  }>()
  const editor = useRef<EditorView>(null)
  const submission = useRef<{ id: string; source: string }>(undefined)
  const size = new TextEncoder().encode(source).length
  const canSubmit = !!source.trim() && size <= 8000
  const validation = checked?.source === source ? checked.result : undefined
  const explicitSelection = data.versions.some((item) => item.selected)

  useEffect(() => {
    try {
      localStorage.setItem(key, source)
    } catch {
      // Черновик остаётся доступен в редакторе.
    }
  }, [key, source])

  async function act(action: string, payload: object, id?: string) {
    setBusy(true)
    setNotice('')
    setActionError('')
    try {
      await socket.send(action, { match_id: data.id, ...payload }, id)
      return true
    } catch (failure) {
      setActionError(
        failure instanceof Error
          ? failure.message
          : 'Не удалось сохранить изменение.',
      )
      return false
    } finally {
      setBusy(false)
    }
  }

  async function submit() {
    if (submission.current?.source !== source)
      submission.current = { id: requestId(), source }
    if (await act('submit_version', { source }, submission.current.id)) {
      submission.current = undefined
      setNotice('Версия отправлена.')
    }
  }

  async function check() {
    setChecking(true)
    setActionError('')
    setNotice('')
    setChecked(undefined)
    try {
      const result = await trainingRequest<Validation>('/validate', {
        method: 'POST',
        body: { source },
      })
      setChecked({ source, result })
    } catch (failure) {
      setActionError(
        failure instanceof Error ? failure.message : 'Проверка недоступна.',
      )
    } finally {
      setChecking(false)
    }
  }

  function jumpTo(line: number) {
    const view = editor.current
    if (!view || view.state.doc.lines < line || line < 1) return
    const target = view.state.doc.line(line)
    view.dispatch({
      selection: { anchor: target.from, head: target.to },
      scrollIntoView: true,
    })
    view.focus()
  }

  return (
    <div className={`algorithm-workspace${training ? ' has-training' : ''}`}>
      <section className="algorithm-panel" aria-labelledby="algorithm-title">
        <div className="training-heading">
          <h3 id="algorithm-title">Алгоритм команды</h3>
          <span className="match-muted">Python · {size} / 8000 байт</span>
        </div>
        <AlgorithmEditor
          editorRef={editor}
          source={source}
          onChange={setSource}
        />
        <div className="match-actions">
          <button
            className="match-button"
            disabled={checking || !canSubmit}
            onClick={() => void check()}
          >
            {checking ? 'Проверяем…' : 'Проверить код'}
          </button>
          <button
            className="match-button is-primary"
            disabled={busy || !online || !canSubmit}
            onClick={() => void submit()}
          >
            Отправить версию
          </button>
          <button
            className="match-button"
            aria-expanded={training}
            onClick={() => setTraining(!training)}
          >
            {training ? 'Закрыть тестовое поле' : 'Открыть тестовое поле'}
          </button>
        </div>
        {actionError && (
          <p className="match-error" role="alert">
            {actionError}
          </p>
        )}
        {notice && (
          <p role="status" className="match-muted">
            {notice}
          </p>
        )}
        {validation?.ok && (
          <p role="status">На контрольном снимке решение корректно.</p>
        )}
        {validation?.error && (
          <div className="match-error" role="alert">
            {validation.error.message}
            {validation.error.line && (
              <button
                className="match-link"
                onClick={() => jumpTo(validation.error!.line!)}
              >
                Строка {validation.error.line}
              </button>
            )}
          </div>
        )}
        <AlgorithmHelp />
        <section
          aria-labelledby="versions-title"
          className="algorithm-versions"
        >
          <h3 id="versions-title">Отправленные версии</h3>
          {data.versions.length ? (
            <ul>
              {data.versions.map((version, index) => (
                <VersionRow
                  key={version.id}
                  version={version}
                  disabled={busy || !online}
                  implicit={
                    index === data.versions.length - 1 && !explicitSelection
                  }
                  onOpen={() => {
                    setSource(version.source)
                    setNotice(`Код «${version.name}» открыт в редакторе.`)
                    editor.current?.focus()
                  }}
                  onSelect={() =>
                    void act('select_version', { version_id: version.id })
                  }
                  onRename={(name) =>
                    act('rename_version', { version_id: version.id, name })
                  }
                />
              ))}
            </ul>
          ) : (
            <p className="match-muted">
              После отправки здесь появится первая версия.
            </p>
          )}
        </section>
      </section>
      {training && <TrainingScreen source={source} />}
    </div>
  )
}
