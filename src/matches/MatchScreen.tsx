import { useEffect, useRef, useState } from 'react'
import CreateMatch from './CreateMatch'
import MatchList from './MatchList'
import MatchLobby from './MatchLobby'
import { getMatchRoute, openMatchRoute, type MatchRoute } from './routes'
import { MatchSocket, type Connection } from './socket'
import './matches.css'

export default function MatchScreen({
  route,
  onExpired,
  onMenu,
}: {
  route: MatchRoute
  onExpired: () => void
  onMenu: () => void
}) {
  const [connection, setConnection] = useState<Connection>('connecting')
  const [socket] = useState(() => new MatchSocket(setConnection, onExpired))
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    socket.open()
    return () => socket.close()
  }, [socket])
  useEffect(() => {
    heading.current?.focus()
  }, [route])

  const online = connection === 'online'
  const title =
    route === 'new'
      ? 'Создать матч'
      : route === 'list'
        ? 'Матчи'
        : 'Матч #' + route
  const previous =
    route === 'new' || route === 'list' ? onMenu : () => openMatchRoute('list')
  function navigate(target: MatchRoute) {
    if (getMatchRoute() === route) openMatchRoute(target)
  }
  return (
    <main className="match-screen" id="main">
      <button className="match-link match-back" onClick={previous}>
        {typeof route === 'number' ? '← К матчам' : '← Главное меню'}
      </button>
      <header className="match-header">
        <h1 ref={heading} tabIndex={-1}>
          {title}
        </h1>
      </header>
      {connection !== 'online' && (
        <div className="match-connection">
          <p role="status">
            {connection === 'offline'
              ? 'Связь прервана. Восстанавливаем подключение…'
              : 'Подключаемся к серверу…'}
          </p>
          {connection === 'offline' && (
            <button className="match-link" onClick={() => socket.reconnect()}>
              Повторить подключение
            </button>
          )}
        </div>
      )}
      {route === 'new' ? (
        <CreateMatch
          socket={socket}
          online={online}
          onCreated={navigate}
          onCancel={onMenu}
        />
      ) : route === 'list' ? (
        <MatchList
          socket={socket}
          online={online}
          onOpen={navigate}
          onCreate={() => navigate('new')}
        />
      ) : (
        <MatchLobby
          key={route}
          socket={socket}
          online={online}
          matchId={route}
          onBack={() => navigate('list')}
        />
      )}
    </main>
  )
}
