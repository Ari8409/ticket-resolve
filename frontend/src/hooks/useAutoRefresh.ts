import { useState, useCallback } from 'react'

export function useAutoRefresh() {
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date())

  const markUpdated = useCallback(() => {
    setLastUpdated(new Date())
  }, [])

  return { autoRefresh, setAutoRefresh, lastUpdated, markUpdated }
}
