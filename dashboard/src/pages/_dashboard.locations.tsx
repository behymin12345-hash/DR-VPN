import { useEffect, useMemo, useState, type ChangeEvent } from 'react'
import { Globe2, MapPin, Search } from 'lucide-react'
import { toast } from 'sonner'

import PageHeader from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  getCoreConfig,
  useGetNodes,
  useModifyCoreConfig,
  useLocationsStatus,
  useStartLocations,
  useStopLocations,
  useInstallTorMl,
  pingLocation,
  CoreResponse,
} from '@/service/api'
import { BALANCER_PORT, LOCATIONS, ccFlag, OUTBOUND_PREFIX } from '@/constants/locations'
import { cn } from '@/lib/utils'

type Binding = Record<string, string> // inboundTag -> location value ('' | 'balancer' | 'T01' | 'P05' ...)

const INSTALL_CMD = 'sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/mrmarzx/Tor-ML-PRO/4.4/tor-ml.sh | tr -d \'\\r\')" -- --install'

const valueToOutbound = (value: string): { tag: string; port: number } | null => {
  if (!value) return null
  if (value === 'balancer') return { tag: `${OUTBOUND_PREFIX}auto`, port: BALANCER_PORT }
  const loc = LOCATIONS.find(l => l.id === value)
  return loc ? { tag: `${OUTBOUND_PREFIX}${loc.cc}-${loc.id}`, port: loc.port } : null
}

export default function LocationsPage() {
  const { data: nodesResp } = useGetNodes()
  const nodes = useMemo(() => nodesResp?.nodes ?? [], [nodesResp])
  const [nodeId, setNodeId] = useState<number | null>(null)
  const [core, setCore] = useState<CoreResponse | null>(null)
  const [binding, setBinding] = useState<Binding>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [pinging, setPinging] = useState<string | null>(null)
  const [pingResults, setPingResults] = useState<Record<string, { ok: boolean; latency?: number; ip?: string }>>({})
  const [search, setSearch] = useState('')
  const statusQuery = useLocationsStatus()
  const status = (statusQuery.data ?? {}) as {
    installed?: boolean
    running_count?: number
    locations?: Array<{ id: string; running: boolean; cc?: string; name?: string; port?: number }>
  }
  const startMutation = useStartLocations()
  const stopMutation = useStopLocations()
  const installMutation = useInstallTorMl()
  const modifyCore = useModifyCoreConfig()

  useEffect(() => {
    if (nodeId === null && nodes.length > 0) setNodeId(nodes[0].id)
  }, [nodes, nodeId])

  const loadCore = async (nid: number) => {
    const node = nodes.find(n => n.id === nid)
    if (!node?.core_config_id) {
      toast.error('This node has no core config')
      return
    }
    setLoading(true)
    try {
      const fetched = await getCoreConfig(node.core_config_id)
      const cfg = JSON.parse(JSON.stringify(fetched.config ?? {})) as Record<string, any>
      const outbounds: any[] = (cfg.outbounds ?? []) as any[]
      const rules: any[] = ((cfg.routing?.rules ?? []) as any[]) ?? []

      const next: Binding = {}
      const outboundsByValue = new Map<string, string>()
      for (const ob of outbounds) {
        const tag = String(ob.tag ?? '')
        if (!tag.startsWith(OUTBOUND_PREFIX)) continue
        let value = ''
        if (tag === OUTBOUND_PREFIX + 'auto') value = 'balancer'
        else {
          const port = Number(ob.settings?.servers?.[0]?.port ?? 0)
          const loc = LOCATIONS.find(l => l.port === port)
          if (loc) value = loc.id
        }
        if (value) {
          outboundsByValue.set(tag, value)
          const rule = rules.find(r => String(r.outboundTag ?? '') === tag)
          if (rule) {
            const inboundTags: string[] = rule.inboundTag ?? []
            for (const it of inboundTags) next[it] = value
          }
        }
      }
      setBinding(next)
      setCore({ ...fetched, config: cfg } as CoreResponse)
    } catch {
      toast.error('Failed to load the core config')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (nodeId !== null && nodes.length) void loadCore(nodeId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeId])

  const inbounds = useMemo<string[]>(() => ((core?.config?.inbounds as any[] | undefined) ?? []).map(i => String(i.tag ?? '')).filter(Boolean), [core])

  const runningById = useMemo(() => {
    const m = new Map<string, boolean>()
    for (const l of status.locations ?? []) m.set(String(l.id), !!l.running)
    return m
  }, [status])

  const doPing = async (locId: string) => {
    setPinging(locId)
    try {
      const res = (await pingLocation(locId)) as { ok?: boolean; latency?: number; ip?: string }
      setPingResults(p => ({ ...p, [locId]: { ok: !!res.ok, latency: res.latency, ip: res.ip } }))
    } catch {
      setPingResults(p => ({ ...p, [locId]: { ok: false } }))
    } finally {
      setPinging(null)
    }
  }

  const toggleLocation = async (locId: string, running: boolean) => {
    try {
      if (running) await stopMutation.mutateAsync({ data: { ids: [locId] } })
      else await startMutation.mutateAsync({ data: { ids: [locId] } })
      await statusQuery.refetch()
    } catch {
      toast.error('Failed — is tor-ml installed on this server?')
    }
  }

  const doInstall = async () => {
    try {
      await installMutation.mutateAsync(undefined)
      toast.success('tor-ml installed')
      await statusQuery.refetch()
    } catch {
      toast.error('Install failed — see server logs')
    }
  }

  const apply = async () => {
    if (!core) return
    setSaving(true)
    try {
      const config = JSON.parse(JSON.stringify(core.config)) as Record<string, any>
      config.outbounds = (config.outbounds ?? []).filter(
        (o: any) => !String(o.tag ?? '').startsWith(OUTBOUND_PREFIX),
      )
      config.routing = config.routing ?? { rules: [] }
      config.routing.rules = (config.routing.rules ?? []).filter(
        (r: any) => !String(r.outboundTag ?? '').startsWith(OUTBOUND_PREFIX),
      )

      const usedValues = new Set<string>()
      for (const tag of inbounds) {
        const v = binding[tag]
        if (v) usedValues.add(v)
      }
      const outboundsByValue = new Map<string, string>()
      for (const v of usedValues) {
        const ob = valueToOutbound(v)
        if (!ob) continue
        outboundsByValue.set(v, ob.tag)
        config.outbounds.push({
          tag: ob.tag,
          protocol: 'socks',
          settings: { servers: [{ address: '127.0.0.1', port: ob.port }] },
        })
      }
      for (const tag of inbounds) {
        const v = binding[tag]
        if (!v) continue
        config.routing.rules.push({
          type: 'field',
          inboundTag: [tag],
          outboundTag: outboundsByValue.get(v),
          network: 'tcp,udp',
        })
      }

      await modifyCore.mutateAsync({
        coreId: core.id,
        data: {
          name: core.name,
          config,
          type: core.type ?? 'xray',
          exclude_inbound_tags: core.exclude_inbound_tags ?? [],
          fallbacks_inbound_tags: core.fallbacks_inbound_tags ?? [],
        },
        params: { restart_nodes: true },
      })
      toast.success('Locations applied — node is restarting with the new routing')
      await loadCore(nodeId!)
    } catch {
      toast.error('Failed to apply — check that the locations are running on the node server')
    } finally {
      setSaving(false)
    }
  }

  const grouped = useMemo(() => ({
    tor: LOCATIONS.filter(l => l.type === 'tor'),
    psiphon: LOCATIONS.filter(l => l.type === 'psiphon'),
  }), [])

  const sortedLocations = useMemo(() => {
    const order = { tor: 0, psiphon: 1 }
    return [...LOCATIONS].sort((a, b) => {
      const ra = runningById.get(a.id) ? 0 : 1
      const rb = runningById.get(b.id) ? 0 : 1
      if (ra !== rb) return ra - rb
      if (order[a.type] !== order[b.type]) return order[a.type] - order[b.type]
      return a.cc.localeCompare(b.cc)
    })
  }, [runningById])

  return (
    <div className="w-full flex-col p-4">
      <PageHeader
        title="Locations"
        description="Route any inbound through a Tor/Psiphon exit country (tor-ml) — users keep the same link, the exit IP changes"
      />
      <Separator className="mb-4" />

      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1">
              <Label>Node</Label>
              <select
                className="border-input bg-background h-10 w-full rounded-md border px-3 text-sm"
                value={nodeId ?? ''}
                onChange={e => setNodeId(Number(e.target.value))}
              >
                {nodes.map(n => (
                  <option key={n.id} value={n.id}>{n.name}</option>
                ))}
              </select>
            </div>
            <Button onClick={apply} disabled={saving || loading || !core || !nodeId}>
              <MapPin className="mr-1 h-4 w-4" />
              {saving ? 'Applying…' : 'Apply & Restart Node'}
            </Button>
          </div>
          <p className="text-muted-foreground text-xs">
            tor-ml must be installed on the node server itself (one command). Install on the node, then start the
            locations you want (<code>tor --start-all-tor</code> or per-location), then bind them here.
          </p>
        </CardContent>
      </Card>

      {loading && <p className="text-muted-foreground p-4 text-sm">Loading core config…</p>}

      <Card className="mb-4">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className={status.installed ? 'h-2 w-2 rounded-full bg-green-500' : 'h-2 w-2 rounded-full bg-zinc-400'} />
              <span className="font-medium">
                {status.installed ? `tor-ml running — ${status.running_count ?? 0} location(s) up` : 'tor-ml is not installed on this server yet'}
              </span>
            </div>
            {!status.installed && (
              <Button onClick={doInstall} disabled={installMutation.isPending}>
                {installMutation.isPending ? 'Installing… (up to 10 min)' : 'Install tor-ml on this server'}
              </Button>
            )}
          </div>

          {status.installed && (
            <div className="mt-4 flex flex-col gap-3">
              <div className="relative">
                <Search className="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2" />
                <Input
                  className="pl-9"
                  placeholder="Search location / country…"
                  value={search}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2 lg:grid-cols-3">
                {sortedLocations
                  .filter(l => {
                    const q = search.trim().toLowerCase()
                    return !q || l.name.toLowerCase().includes(q) || l.cc.toLowerCase().includes(q) || l.id.toLowerCase().includes(q) || (l.type === 'tor' && 'tor'.includes(q)) || (l.type === 'psiphon' && 'psiphon'.includes(q))
                  })
                  .map(l => {
                    const running = runningById.get(l.id) ?? false
                    const pr = pingResults[l.id]
                    return (
                      <div key={l.id} className="border-input flex items-center justify-between gap-2 rounded-md border p-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className={running ? 'h-2 w-2 shrink-0 rounded-full bg-green-500' : 'h-2 w-2 shrink-0 rounded-full bg-zinc-400'} />
                          <span className="shrink-0 text-base leading-none">{ccFlag(l.cc)}</span>
                          <span className="truncate text-sm">{l.cc} — {l.name}</span>
                          <span className={cn('shrink-0 rounded px-1 py-0.5 text-[10px]', l.type === 'tor' ? 'bg-purple-500/15 text-purple-500' : 'bg-sky-500/15 text-sky-500')}>
                            {l.type === 'tor' ? 'Tor' : 'Psiphon'}
                          </span>
                          <span className="text-muted-foreground text-[10px]">:{l.port}</span>
                        </div>
                        <div className="flex shrink-0 items-center gap-1">
                          {pr && (
                            <span className={pr.ok ? 'text-xs text-green-600' : 'text-xs text-red-500'}>
                              {pr.ok ? `${Math.round((pr.latency ?? 0) * 1000)}ms` : 'fail'}
                            </span>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs"
                            disabled={pinging === l.id}
                            onClick={() => doPing(l.id)}
                          >
                            ping
                          </Button>
                          <Button
                            variant={running ? 'outline' : 'default'}
                            size="sm"
                            className="h-7 px-2 text-xs"
                            onClick={() => toggleLocation(l.id, running)}
                          >
                            {running ? 'Stop' : 'Start'}
                          </Button>
                        </div>
                      </div>
                    )
                  })}
              </div>
              {sortedLocations.filter(l => {
                const q = search.trim().toLowerCase()
                return q && !(l.name.toLowerCase().includes(q) || l.cc.toLowerCase().includes(q) || l.id.toLowerCase().includes(q))
              }).length > 0 && (
                <p className="text-muted-foreground text-center text-xs">No location matches your search</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {!!inbounds.length && !loading && (
        <div className="flex flex-col gap-3">
          {inbounds.map(tag => (
            <Card key={tag}>
              <CardContent className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-40 flex-1">
                  <span className="font-medium">{tag}</span>
                  <p className="text-muted-foreground text-xs">inbound</p>
                </div>
                <div className="min-w-64 flex-1">
                  <select
                    className="border-input bg-background h-10 w-full rounded-md border px-3 text-sm"
                    value={binding[tag] ?? ''}
                    onChange={e => setBinding(b => ({ ...b, [tag]: e.target.value }))}
                  >
                    <option value="">Direct (no location)</option>
                    <option value="balancer">⚡ Auto Balancer (best ping)</option>
                    <optgroup label="Tor (60)">
                      {(grouped.tor as { id: string; cc: string; name: string; port: number }[]).map((l: { id: string; cc: string; name: string; port: number }) => (
                        <option key={l.id} value={l.id}>{ccFlag(l.cc)} {l.cc} — {l.name} (:{l.port})</option>
                      ))}
                    </optgroup>
                    <optgroup label="Psiphon (28)">
                      {(grouped.psiphon as { id: string; cc: string; name: string; port: number }[]).map((l: { id: string; cc: string; name: string; port: number }) => (
                        <option key={l.id} value={l.id}>{ccFlag(l.cc)} {l.cc} — {l.name} (:{l.port})</option>
                      ))}
                    </optgroup>
                  </select>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card className="mt-4">
        <CardContent className="p-4">
          <div className="mb-2 flex items-center gap-2">
            <Globe2 className="h-4 w-4" />
            <span className="font-medium">Install tor-ml on a node server (once)</span>
          </div>
          <pre dir="ltr" className="bg-muted overflow-x-auto rounded p-3 text-xs">{INSTALL_CMD}</pre>
          <p className="text-muted-foreground mt-2 text-xs">
            Then: <code>tor --mode weak</code> (small VPS) and <code>tor --start T01 T03</code> +{' '}
            <code>tor --balancer-start</code>. 1 GB RAM ≈ max 8 locations; DE/NL/FR/GB have the best ping.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
