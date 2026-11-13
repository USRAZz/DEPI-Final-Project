import { useEffect, useState } from 'react'

type State<T> = { status: 'loading' } | { status: 'error'; error: Error } | { status: 'ready'; data: T }

/** Runs a loader when its deps change and ignores results from stale runs. */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({ status: 'loading' })

  useEffect(() => {
    let active = true
    setState({ status: 'loading' })
    load().then(
      (data) => active && setState({ status: 'ready', data }),
      (error: Error) => active && setState({ status: 'error', error }),
    )
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}
