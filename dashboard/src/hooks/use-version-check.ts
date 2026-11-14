import { useSystemUpdateCheck } from '@/service/api'

interface VersionCheckResult {
  hasUpdate: boolean
  latestVersion: string | null
  currentVersion: string | null
  releaseUrl: string | null
  isLoading: boolean
}

interface UseVersionCheckOptions {
  enabled?: boolean
}

const CHECK_STALE_TIME = 10 * 60 * 1000

/**
 * Update check backed by the panel itself (`GET /api/system/update-check`).
 *
 * The panel fetches the latest GitHub release server-side and caches it for
 * 30 minutes: browsers in censored networks (e.g. Iran) cannot reach
 * api.github.com, which silently disabled the old client-side check.
 */
export function useVersionCheck(_currentVersion: string | null, options: UseVersionCheckOptions = {}): VersionCheckResult {
  void _currentVersion // the comparison happens server-side against the running panel version
  const enabled = options.enabled ?? true
  const { data, isLoading } = useSystemUpdateCheck({
    query: {
      enabled,
      staleTime: CHECK_STALE_TIME,
      gcTime: CHECK_STALE_TIME * 2,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      refetchInterval: CHECK_STALE_TIME,
      retry: 1,
    },
  })

  return {
    hasUpdate: !!data?.update_available,
    latestVersion: data?.latest_version ?? null,
    currentVersion: data?.current_version ?? null,
    releaseUrl: data?.release_url ?? null,
    isLoading: enabled ? isLoading : false,
  }
}
