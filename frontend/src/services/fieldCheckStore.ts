import { useSyncExternalStore } from 'react'
import { load, persist, type FieldCheck } from './fieldChecks'

// One shared list for every panel. Changes are written straight to this browser's storage.
let list: FieldCheck[] | null = null
let saved = true
const listeners = new Set<() => void>()

const get = () => (list ??= load())

export function updateChecks(fn: (l: FieldCheck[]) => FieldCheck[]) {
  list = fn(get())
  saved = persist(list)
  listeners.forEach((f) => f())
}

const subscribe = (f: () => void) => { listeners.add(f); return () => { listeners.delete(f) } }

export function useChecks(): { checks: FieldCheck[]; saved: boolean } {
  const checks = useSyncExternalStore(subscribe, get, get)
  return { checks, saved }
}

// for tests
export function resetChecks(l: FieldCheck[] | null = null) { list = l; saved = true; listeners.forEach((f) => f()) }
