export type MatchRoute = 'list' | 'new' | number

export function getMatchRoute(): MatchRoute | null {
  const hash = window.location.hash
  if (hash === '#/matches') return 'list'
  if (hash === '#/matches/new') return 'new'
  const id = Number(/^#\/matches\/([1-9]\d*)$/.exec(hash)?.[1])
  return Number.isSafeInteger(id) ? id : null
}

export function watchMatchRoute(listener: () => void) {
  window.addEventListener('hashchange', listener)
  return () => window.removeEventListener('hashchange', listener)
}

export function openMatchRoute(route: MatchRoute | null) {
  const hash =
    route === null
      ? '#main'
      : route === 'list'
        ? '#/matches'
        : '#/matches/' + route
  window.location.hash = hash
}
