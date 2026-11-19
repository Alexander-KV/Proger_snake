import type { Cell } from '../matches/socket'

export type Bot = 'random' | 'hunter' | 'pathfinding' | 'survival'
export const botNames: Record<Bot, string> = {
  random: 'Random Bot',
  hunter: 'Food Hunter',
  pathfinding: 'Pathfinding Bot',
  survival: 'Survival Bot',
}

export type Config = {
  width: number
  height: number
  snake_count: number
  tick_limit: number
  obstacles: number
  water: number
  normal: number
  gold: number
  poison: number
  shields: number
}

export const defaultConfig: Config = {
  width: 16,
  height: 12,
  snake_count: 2,
  tick_limit: 300,
  obstacles: 6,
  water: 12,
  normal: 4,
  gold: 1,
  poison: 2,
  shields: 1,
}

export type Result = {
  id: number
  name: string
  score: number
  length: number
  alive: boolean
  place: number
}

export type Arena = {
  width: number
  height: number
  tick: number
  tick_limit: number
  snakes: (Omit<Result, 'place'> & {
    body: Cell[]
    head: Cell | null
    effects?: { shield_ticks: number }
    movement: { progress: number; in_water: boolean; slowed: boolean } | null
  })[]
  obstacles: Cell[]
  water: Cell[]
  food: { cell: Cell; kind: 'normal' | 'gold' }[]
  poison: Cell[]
  powerups: { cell: Cell; kind: 'shield' }[]
  winners: number[]
  finished: boolean
  results: Result[]
}

export type AlgorithmIssue = {
  message: string
  code: string
  line: number | null
  tick?: number
}

export type Validation = { ok: boolean; error: AlgorithmIssue | null }
export type Draft = { config: Config; seed: number; cleared: boolean }
export type PreparedMap = {
  id?: number
  name?: string
  draft: Draft
  arena: Arena
  bots?: Bot[]
}
export type MapOption = { id: number; name: string }
export type Run = { id: string; arena: Arena; error: AlgorithmIssue | null }

export async function trainingRequest<T>(
  path: string,
  options: { method?: string; body?: object; acceptConflict?: boolean } = {},
): Promise<T> {
  const response = await fetch('/api/training' + path, {
    method: options.method,
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })
  if (response.status === 204) return undefined as T
  const data = (await response.json().catch(() => null)) as {
    detail?: unknown
  } | null
  if (!response.ok && !(options.acceptConflict && response.status === 409)) {
    const detail = data?.detail
    throw new Error(
      typeof detail === 'string'
        ? detail
        : response.status === 422
          ? 'Проверьте настройки поля и размер исходного кода.'
          : 'Не удалось выполнить запрос. Попробуйте ещё раз.',
    )
  }
  return data as T
}
