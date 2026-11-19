import { useEffect, useState } from 'react'

export default function PreparationClock({
  endsAt,
  serverTime,
}: {
  endsAt: number
  serverTime: number
}) {
  const [deadline] = useState(
    () => performance.now() + (endsAt - serverTime) * 1000,
  )
  const [seconds, setSeconds] = useState(() =>
    Math.max(0, Math.ceil(endsAt - serverTime)),
  )

  useEffect(() => {
    const timer = window.setInterval(
      () =>
        setSeconds(
          Math.max(0, Math.ceil((deadline - performance.now()) / 1000)),
        ),
      250,
    )
    return () => window.clearInterval(timer)
  }, [deadline])

  const time = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
  return (
    <div className="preparation-clock">
      <strong>
        {seconds
          ? 'Подготовка алгоритмов'
          : 'Подготовка завершена. Ожидаем матч…'}
      </strong>
      {seconds > 0 && (
        <span role="timer" aria-label={`До матча ${time}`}>
          {time}
        </span>
      )}
    </div>
  )
}
