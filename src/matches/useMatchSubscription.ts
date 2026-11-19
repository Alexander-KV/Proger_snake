import { useEffect, useState } from 'react'
import {
  MatchError,
  MatchSocket,
  type MatchSnapshot,
  type MatchView,
} from './socket'

export default function useMatchSubscription(
  socket: MatchSocket,
  view: MatchView,
) {
  const [data, setData] = useState<MatchSnapshot>()
  const [error, setError] = useState<MatchError>()
  const [attempt, setAttempt] = useState(0)
  const matchId = view.view === 'lobby' ? view.match_id : undefined

  useEffect(
    () =>
      socket.subscribe(
        matchId === undefined
          ? { view: 'list' }
          : { view: 'lobby', match_id: matchId },
        (snapshot) => {
          setData(snapshot)
          setError(undefined)
        },
        (failure) => {
          setData(undefined)
          setError(failure)
        },
      ),
    [socket, matchId, attempt],
  )

  function retry() {
    setError(undefined)
    setAttempt((previous) => previous + 1)
  }

  return { data, error, retry }
}
