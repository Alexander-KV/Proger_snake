import { useEffect, useRef, useState } from 'react'

type Team = { username: string; name: string }
type Props = { mode: 'login' | 'register' | 'required'; onClose: () => void; onMode: (mode: Props['mode']) => void; onSuccess: (team: Team) => void }

export default function AuthDialog({ mode, onClose, onMode, onSuccess }: Props) {
  const [username, setUsername] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { dialog.current?.showModal() }, [])
  const errors = {
    username: !username ? 'Введите username.' : !/^[A-Za-z0-9_]{1,15}$/.test(username) ? 'До 15 английских букв, цифр или знаков подчёркивания, без пробелов.' : '',
    name: !name.trim() ? 'Введите название.' : !/^[0-9]{1,15}$/.test(name.trim()) ? 'Название должно содержать только цифры, не более 15.' : '',
    password: !password ? 'Введите пароль.' : mode === 'register' && password.length < 4 ? 'Не менее 4 символов.' : '',
  }
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = mode === 'register' ? ['username', 'name', 'password'] as const : ['username', 'password'] as const
    setTouched(Object.fromEntries(fields.map(field => [field, true])))
    const first = fields.find(field => errors[field])
    if (first) { document.getElementById(`auth-${first}`)?.focus(); return }
    setBusy(true); setError('')
    try {
      const response = await fetch(`/api/auth/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username, name: name.trim(), password }) })
      if (!response.ok) {
        if (response.status === 409) { setError('Этот username уже занят.'); document.getElementById('auth-username')?.focus() }
        else if (response.status === 401) setError('Неверный username или пароль.')
        else if (response.status === 429) setError('Слишком много попыток. Попробуйте через минуту.')
        else setError('Не удалось выполнить запрос. Попробуйте ещё раз.')
        return
      }
      onSuccess(await response.json() as Team)
    } catch { setError('Не удалось связаться с сервером.') } finally { setBusy(false) }
  }
  function field(id: keyof typeof errors, label: string, value: string, change: (value: string) => void, hint: string, type = 'text') {
    const invalid = Boolean(touched[id] && errors[id])
    return <div className="auth-field"><label htmlFor={`auth-${id}`}>{label}</label><input id={`auth-${id}`} type={type} value={value} onChange={event => { change(event.target.value); if (id === 'username') setTouched(current => ({ ...current, username: true })) }} onBlur={() => setTouched(current => ({ ...current, [id]: true }))} aria-invalid={invalid} aria-describedby={`hint-${id}`} autoComplete={id === 'password' ? (mode === 'register' ? 'new-password' : 'current-password') : id === 'username' ? 'username' : 'off'} /><small id={`hint-${id}`} className={invalid ? 'field-error' : ''}>{invalid ? errors[id] : hint}</small></div>
  }
  return <dialog ref={dialog} className="auth-dialog" onCancel={event => { event.preventDefault(); onClose() }} onClick={event => { if (event.target === dialog.current) onClose() }}>
    <div className="auth-dialog-header"><h2>{mode === 'required' ? 'Нужна регистрация' : mode === 'login' ? 'Вход' : 'Регистрация'}</h2><button type="button" className="dialog-close" onClick={onClose} aria-label="Закрыть">×</button></div>
    {mode === 'required' ? <><p>Чтобы открыть этот раздел, зарегистрируйтесь или войдите в команду.</p><div className="auth-actions"><button className="auth-primary" onClick={() => onMode('register')}>Зарегистрироваться</button><button onClick={() => onMode('login')}>Войти</button></div></> : <form onSubmit={submit} noValidate>
      {field('username', 'Username команды', username, setUsername, 'Уникальное имя для входа: до 15 английских букв, цифр и _.')}
      {mode === 'register' && field('name', 'Название команды', name, setName, 'Отображается другим: до 15 цифр.')}
      {field('password', 'Пароль', password, setPassword, mode === 'register' ? 'Для входа, не менее 4 символов.' : 'Пароль вашей команды.', 'password')}
      {error && <p className="field-error" role="alert">{error}</p>}
      <button className="auth-primary" disabled={busy}>{busy ? 'Подождите…' : mode === 'login' ? 'Войти' : 'Зарегистрироваться'}</button>
      <button className="auth-switch" type="button" onClick={() => onMode(mode === 'login' ? 'register' : 'login')}>{mode === 'login' ? 'Нет команды? Зарегистрироваться' : 'Уже есть команда? Войти'}</button>
    </form>}
  </dialog>
}
