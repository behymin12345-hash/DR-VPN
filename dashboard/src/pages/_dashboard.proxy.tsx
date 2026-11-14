import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  Ban,
  CheckCircle2,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  Link as LinkIcon,
  Pencil,
  QrCode,
  RefreshCcw,
  Server as ServerIcon,
  Trash2,
  UserPlus,
} from 'lucide-react'
import { QRCodeCanvas } from 'qrcode.react'
import { toast } from 'sonner'

import PageHeader from '@/components/layout/page-header'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  MtprotoProxyResponse,
  ProxyClientCreate,
  ProxyClientModify,
  UserListItem,
  useCreateMtprotoProxy,
  useCreateProxyClient,
  useGetMtprotoProxies,
  useGetProxyClients,
  useGetAllGroups,
  getGetMtprotoProxiesQueryKey,
  getGetProxyClientsQueryKey,
  useModifyMtprotoProxy,
  useModifyProxyClient,
  useRemoveMtprotoProxy,
  useRemoveProxyClient,
  useGetNodes,
} from '@/service/api'
import { useClipboard } from '@/hooks/use-clipboard'
import { formatBytes } from '@/utils/formatByte'

const GB = 1024 ** 3
const DAY = 86400

const generateMtprotoSecret = () => {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

const fullSecret = (p: { secret: string; tag?: string | null }) => p.tag ? `dd${p.tag}${p.secret}` : p.secret
const tgLink = (p: { server: string; port: number; secret: string; tag?: string | null }) =>
  `tg://proxy?server=${p.server}&port=${p.port}&secret=${fullSecret(p)}`
const httpsLink = (p: { server: string; port: number; secret: string; tag?: string | null }) =>
  `https://t.me/proxy?server=${p.server}&port=${p.port}&secret=${fullSecret(p)}`

const absoluteSubLink = (url?: string | null) =>
  !url ? '' : url.startsWith('http') ? url : `${window.location.origin}${url}`

const expireDate = (expire?: string | number | null) => {
  if (expire === null || expire === undefined) return null
  const ms = typeof expire === 'number' ? expire * 1000 : Date.parse(expire)
  return Number.isNaN(ms) ? null : ms
}

const statusColor = (status: string) =>
  status === 'active'
    ? 'bg-green-500'
    : status === 'disabled'
      ? 'bg-zinc-400'
      : status === 'on_hold'
        ? 'bg-blue-400'
        : 'bg-red-400'

interface ProxyFormValue {
  name: string
  server: string
  port: string
  secret: string
  enabled: boolean
  sponsoredChannel: string
  tag: string
  nodeId: string
  groupId: string
}

const emptyProxyForm: ProxyFormValue = {
  name: '',
  server: '',
  port: '443',
  secret: '',
  enabled: true,
  sponsoredChannel: '',
  tag: '',
  nodeId: '',
  groupId: '',
}

interface ClientFormValue {
  username: string
  dataLimitGb: string
  expireDays: string
  coefficient: string
  groupIds: number[]
}

const emptyClientForm: ClientFormValue = {
  username: '',
  dataLimitGb: '',
  expireDays: '',
  coefficient: '1',
  groupIds: [],
}

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-muted-foreground text-xs">{label}</p>
        <p className="mt-1 text-xl font-semibold">{value}</p>
        {hint && <p className="text-muted-foreground text-[11px]">{hint}</p>}
      </CardContent>
    </Card>
  )
}

export default function ProxyPage() {
  const { data: proxies = [], isLoading: proxiesLoading } = useGetMtprotoProxies()
  const { data: clientsResp, isLoading: clientsLoading } = useGetProxyClients()
  const { data: groupsResp } = useGetAllGroups()
  const { data: nodesResp } = useGetNodes()
  const groups = groupsResp?.groups ?? []
  const nodes = nodesResp?.nodes ?? []
  // Proxy-only groups: a group with no inbounds carries Telegram proxies instead of configs.
  const proxyGroups = useMemo(
    () => groups.filter((g: { id: number; inbound_tags?: string[] | null }) => !g.inbound_tags || g.inbound_tags.length === 0),
    [groups],
  )
  const clients: UserListItem[] = useMemo(() => clientsResp?.users ?? [], [clientsResp])
  const activeClients = clients.filter((c) => c.status === 'active').length
  const clientsTraffic = clients.reduce((sum, c) => sum + (c.used_traffic || 0), 0)

  const queryClient = useQueryClient()
  const { copy } = useClipboard()

  const invalidateClients = () => queryClient.invalidateQueries({ queryKey: getGetProxyClientsQueryKey() })
  const invalidateProxies = () => queryClient.invalidateQueries({ queryKey: getGetMtprotoProxiesQueryKey() })

  // --- proxy state
  const [proxyDialogOpen, setProxyDialogOpen] = useState(false)
  const [editingProxy, setEditingProxy] = useState<MtprotoProxyResponse | null>(null)
  const [proxyForm, setProxyForm] = useState<ProxyFormValue>(emptyProxyForm)
  const [qrLink, setQrLink] = useState<string | null>(null)
  const [deleteProxyTarget, setDeleteProxyTarget] = useState<MtprotoProxyResponse | null>(null)
  const [proxySearch, setProxySearch] = useState('')
  const [proxySort, setProxySort] = useState<{ key: 'name' | 'server' | 'port' | 'node'; dir: 1 | -1 }>({
    key: 'name',
    dir: 1,
  })
  const [groupByServer, setGroupByServer] = useState(true)
  const [revealedSecrets, setRevealedSecrets] = useState<number[]>([])

  // --- client state
  const [clientSearch, setClientSearch] = useState('')
  const [clientDialogOpen, setClientDialogOpen] = useState(false)
  const [editingClient, setEditingClient] = useState<UserListItem | null>(null)
  const [clientForm, setClientForm] = useState<ClientFormValue>(emptyClientForm)
  const [deleteClientTarget, setDeleteClientTarget] = useState<UserListItem | null>(null)

  const createProxyMutation = useCreateMtprotoProxy()
  const modifyProxyMutation = useModifyMtprotoProxy()
  const removeProxyMutation = useRemoveMtprotoProxy()

  const createClientMutation = useCreateProxyClient()
  const modifyClientMutation = useModifyProxyClient()
  const removeClientMutation = useRemoveProxyClient()

  // ---------------------------------------------------------------- proxies
  const openProxyCreate = () => {
    setEditingProxy(null)
    setProxyForm(emptyProxyForm)
    setProxyDialogOpen(true)
  }

  const openProxyEdit = (proxy: MtprotoProxyResponse) => {
    setEditingProxy(proxy)
    setProxyForm({
      name: proxy.name,
      server: proxy.server,
      port: String(proxy.port),
      secret: proxy.secret,
      enabled: !!proxy.enabled,
      sponsoredChannel: proxy.sponsored_channel ?? '',
      tag: proxy.tag ?? '',
      nodeId: proxy.node_id ? String(proxy.node_id) : '',
      groupId: proxy.group_id ? String(proxy.group_id) : '',
    })
    setProxyDialogOpen(true)
  }

  const submitProxy = async () => {
    const payload = {
      name: proxyForm.name.trim(),
      server: proxyForm.server.trim(),
      port: Number(proxyForm.port),
      secret: proxyForm.secret.trim() || generateMtprotoSecret(),
      enabled: proxyForm.enabled,
      sponsored_channel: proxyForm.sponsoredChannel.trim() || null,
      tag: proxyForm.tag.trim() || null,
      node_id: proxyForm.nodeId ? Number(proxyForm.nodeId) : null,
    }
    if (!payload.name || !payload.server || !payload.port) {
      toast.error('Name, server and port are required')
      return
    }
    try {
      if (editingProxy) {
        await modifyProxyMutation.mutateAsync({ proxyId: editingProxy.id, data: payload })
        toast.success('Proxy updated')
      } else {
        await createProxyMutation.mutateAsync({ data: payload })
        toast.success('Proxy created')
      }
      setProxyDialogOpen(false)
      invalidateProxies()
    } catch {
      toast.error('Failed — the name may already exist')
    }
  }

  const confirmDeleteProxy = async () => {
    if (!deleteProxyTarget) return
    try {
      await removeProxyMutation.mutateAsync({ proxyId: deleteProxyTarget.id })
      toast.success('Proxy deleted')
      setDeleteProxyTarget(null)
      invalidateProxies()
    } catch {
      toast.error('Failed to delete')
    }
  }

  const toggleProxyEnabled = async (proxy: MtprotoProxyResponse, enabled: boolean) => {
    try {
      await modifyProxyMutation.mutateAsync({
        proxyId: proxy.id,
        data: {
          name: proxy.name,
          server: proxy.server,
          port: proxy.port,
          secret: proxy.secret,
          enabled,
          sponsored_channel: proxy.sponsored_channel ?? null,
          tag: proxy.tag ?? null,
          node_id: proxy.node_id ?? null,
        },
      })
      invalidateProxies()
    } catch {
      toast.error('Failed to update')
    }
  }

  // ---------------------------------------------------------------- clients
  const openClientCreate = () => {
    setEditingClient(null)
    setClientForm({
      ...emptyClientForm,
      groupIds: proxyGroups[0] ? [proxyGroups[0].id] : [],
    })
    setClientDialogOpen(true)
  }

  const openClientEdit = (client: UserListItem) => {
    setEditingClient(client)
    setClientForm({
      username: client.username,
      dataLimitGb: client.data_limit ? String(Math.round((client.data_limit / GB) * 100) / 100) : '',
      expireDays: '',
      coefficient: client.usage_coefficient ? String(client.usage_coefficient) : '1',
      groupIds: client.group_ids ?? [],
    })
    setClientDialogOpen(true)
  }

  const submitClient = async () => {
    const username = clientForm.username.trim()
    if (!username) {
      toast.error('Username is required')
      return
    }
    if (clientForm.groupIds.length === 0) {
      toast.error('Pick at least one proxy group')
      return
    }
    const dataLimit = clientForm.dataLimitGb.trim() ? Math.round(Number(clientForm.dataLimitGb) * GB) : null
    const expire = clientForm.expireDays.trim()
      ? Math.floor(Date.now() / 1000) + Number(clientForm.expireDays) * DAY
      : null
    const coefficient = clientForm.coefficient.trim() ? Number(clientForm.coefficient) : null
    if (coefficient !== null && (Number.isNaN(coefficient) || coefficient <= 0)) {
      toast.error('Usage coefficient must be a positive number')
      return
    }
    try {
      if (editingClient) {
        const data: ProxyClientModify = {
          group_ids: clientForm.groupIds,
          data_limit: dataLimit,
          expire,
          usage_coefficient: coefficient,
        }
        await modifyClientMutation.mutateAsync({ username: editingClient.username, data })
        toast.success('Client updated')
      } else {
        const data: ProxyClientCreate = {
          username,
          group_ids: clientForm.groupIds,
          data_limit: dataLimit,
          expire,
          usage_coefficient: coefficient,
        }
        await createClientMutation.mutateAsync({ data })
        toast.success(`Client "${username}" created`)
      }
      setClientDialogOpen(false)
      invalidateClients()
      invalidateProxies()
    } catch {
      toast.error('Failed — the username may already exist')
    }
  }

  const toggleClientStatus = async (client: UserListItem) => {
    const status = client.status === 'disabled' ? 'active' : 'disabled'
    try {
      await modifyClientMutation.mutateAsync({ username: client.username, data: { status } })
      toast.success(status === 'active' ? 'Client enabled' : 'Client disabled')
      invalidateClients()
    } catch {
      toast.error('Failed to update')
    }
  }

  const confirmDeleteClient = async () => {
    if (!deleteClientTarget) return
    try {
      await removeClientMutation.mutateAsync({ username: deleteClientTarget.username })
      toast.success('Client deleted')
      setDeleteClientTarget(null)
      invalidateClients()
      invalidateProxies()
    } catch {
      toast.error('Failed to delete')
    }
  }

  const filteredClients = useMemo(() => {
    const q = clientSearch.trim().toLowerCase()
    return q ? clients.filter((c) => c.username.toLowerCase().includes(q)) : clients
  }, [clients, clientSearch])

  // ------------------------------------------------------- proxy table logic
  const nodeName = (id?: number | null) =>
    id ? (nodes.find((n: { id: number; name: string }) => n.id === id)?.name ?? `node #${id}`) : '—'

  const sortedProxies = useMemo(() => {
    const q = proxySearch.trim().toLowerCase()
    const list = q ? proxies.filter((p) => `${p.name} ${p.server}`.toLowerCase().includes(q)) : [...proxies]
    list.sort((a, b) => {
      if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
      const { key, dir } = proxySort
      const av = key === 'node' ? nodeName(a.node_id) : String(a[key])
      const bv = key === 'node' ? nodeName(b.node_id) : String(b[key])
      return av.localeCompare(bv) * dir
    })
    return list
  }, [proxies, proxySearch, proxySort, nodes])

  const serverGroups = useMemo(() => {
    if (!groupByServer) return [{ server: '', proxies: sortedProxies }]
    const map = new Map<string, MtprotoProxyResponse[]>()
    for (const p of sortedProxies) {
      const key = nodeName(p.node_id) === '—' ? 'This panel server (local mtg)' : nodeName(p.node_id)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(p)
    }
    return [...map.entries()].map(([server, list]) => ({ server, proxies: list }))
  }, [sortedProxies, groupByServer, nodes])

  const toggleSort = (key: 'name' | 'server' | 'port' | 'node') =>
    setProxySort((s) => (s.key === key ? { key, dir: (s.dir * -1) as 1 | -1 } : { key, dir: 1 }))

  const sortIcon = (key: 'name' | 'server' | 'port' | 'node') =>
    proxySort.key === key ? (proxySort.dir === 1 ? ' ▲' : ' ▼') : ''

  const toggleReveal = (id: number) =>
    setRevealedSecrets((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]))

  const groupBadge = (ids?: number[] | null) =>
    (ids ?? [])
      .map((id) => groups.find((g: { id: number; name: string }) => g.id === id))
      .filter(Boolean)
      .map((g) => (g as { name: string }).name)

  return (
    <div className="w-full flex-col p-4">
      <PageHeader
        title="Proxy Workspace"
        description="A fully separate workspace for Telegram proxy clients and MTProto proxies — config users, groups and cores live on the Users/Groups pages"
        buttonText="Add Client"
        onButtonClick={openClientCreate}
      />
      <Separator className="mb-4" />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Proxies" value={String(proxies.length)} hint={`${proxies.filter((p) => p.enabled).length} enabled`} />
        <StatCard label="Clients" value={String(clientsResp?.total ?? clients.length)} hint="proxy groups only" />
        <StatCard label="Active" value={String(activeClients)} hint="clients online-eligible" />
        <StatCard label="Client traffic" value={formatBytes(clientsTraffic)} hint="all-time usage" />
      </div>

      <Tabs defaultValue="clients" className="w-full">
        <TabsList>
          <TabsTrigger value="clients">Clients</TabsTrigger>
          <TabsTrigger value="proxies">Proxies</TabsTrigger>
        </TabsList>

        {/* ------------------------------------------------ Clients tab */}
        <TabsContent value="clients" className="mt-3">
          <div className="mb-3 flex items-center gap-2">
            <Input
              value={clientSearch}
              onChange={(e) => setClientSearch(e.target.value)}
              placeholder="Search clients…"
              className="max-w-xs"
            />
            <Button onClick={openClientCreate} size="sm">
              <UserPlus className="h-4 w-4" /> Add Client
            </Button>
          </div>

          {clientsLoading ? (
            <p className="text-muted-foreground p-4 text-sm">Loading…</p>
          ) : proxyGroups.length === 0 ? (
            <Card>
              <CardContent className="text-muted-foreground p-10 text-center text-sm">
                No proxy group exists yet. Create a group without any inbounds on the Groups page, then clients
                created here will live in it — fully separate from config users.
              </CardContent>
            </Card>
          ) : filteredClients.length === 0 ? (
            <Card>
              <CardContent className="text-muted-foreground p-10 text-center text-sm">
                No clients yet — click "Add Client" to create a Telegram-proxy client with its own quota and expiry.
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {filteredClients.map((client) => {
                const usedPct = client.data_limit ? Math.min(100, ((client.used_traffic || 0) / client.data_limit) * 100) : 0
                const subLink = absoluteSubLink(client.subscription_url)
                const expiry = expireDate(client.expire)
                return (
                  <Card key={client.id}>
                    <CardContent className="flex flex-col gap-2 p-4">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className={`h-2 w-2 shrink-0 rounded-full ${statusColor(client.status)}`} />
                          <span className="truncate font-medium">{client.username}</span>
                          <div className="flex gap-1">
                            {groupBadge(client.group_ids).map((name) => (
                              <Badge key={name} variant="secondary" className="text-[10px]">
                                {name}
                              </Badge>
                            ))}
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            title={client.status === 'disabled' ? 'Enable' : 'Disable'}
                            onClick={() => toggleClientStatus(client)}
                          >
                            {client.status === 'disabled' ? (
                              <CheckCircle2 className="h-4 w-4" />
                            ) : (
                              <Ban className="h-4 w-4" />
                            )}
                          </Button>
                          <Button variant="ghost" size="icon" title="Edit" onClick={() => openClientEdit(client)}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="icon" onClick={() => setDeleteClientTarget(client)}>
                            <Trash2 className="text-destructive h-4 w-4" />
                          </Button>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-muted-foreground">
                          {formatBytes(client.used_traffic || 0)}
                          {client.data_limit ? ` / ${formatBytes(client.data_limit)}` : ' / unlimited'}
                        </span>
                        {client.data_limit ? (
                          <Progress value={usedPct} className="h-1.5 flex-1" />
                        ) : (
                          <span className="flex-1" />
                        )}
                        <span className="text-muted-foreground shrink-0">
                          {expiry ? `exp ${new Date(expiry).toLocaleDateString()}` : 'never expires'}
                        </span>
                        {!!client.usage_coefficient && client.usage_coefficient !== 1 && (
                          <Badge variant="outline" className="text-[10px]">
                            ×{client.usage_coefficient}
                          </Badge>
                        )}
                      </div>

                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1"
                          onClick={async () => {
                            if (!subLink) return toast.error('No subscription link yet')
                            await copy(subLink)
                            toast.success('Subscription link copied')
                          }}
                        >
                          <Copy className="h-3 w-3" /> Sub link
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => subLink && window.open(subLink, '_blank')}
                          title="Open subscription page"
                        >
                          <ExternalLink className="h-3 w-3" />
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                )
              })}
            </div>
          )}
        </TabsContent>

        {/* ------------------------------------------------ Proxies tab */}
        <TabsContent value="proxies" className="mt-3">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Button onClick={openProxyCreate} size="sm">
              <QrCode className="h-4 w-4" /> Add Proxy
            </Button>
            <Input
              value={proxySearch}
              onChange={(e) => setProxySearch(e.target.value)}
              placeholder="Search proxies…"
              className="max-w-56"
            />
            <label className="text-muted-foreground flex cursor-pointer items-center gap-1.5 text-xs">
              <input type="checkbox" checked={groupByServer} onChange={(e) => setGroupByServer(e.target.checked)} />
              group by server
            </label>
            <Badge variant="outline" className="border-violet-500/40 text-violet-500">
              MTProto inbound — separate from config inbounds (VLESS/VMess)
            </Badge>
          </div>

          {proxiesLoading ? (
            <p className="text-muted-foreground p-4 text-sm">Loading…</p>
          ) : proxies.length === 0 ? (
            <Card>
              <CardContent className="text-muted-foreground p-10 text-center text-sm">
                No Telegram proxies yet — click "Add Proxy" to create one (enter the secret from `drvpn
                install-mtproto` or leave it empty to auto-generate), and edit it any time.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4">
              {serverGroups.map(({ server, proxies: groupList }) => (
                <div key={server || 'all'}>
                  {server && (
                    <p className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium">
                      <ServerIcon className="h-3.5 w-3.5" /> {server}
                    </p>
                  )}
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-muted-foreground border-b text-left text-xs">
                        <th
                          className="cursor-pointer py-2 pl-2"
                          onClick={() => toggleSort('name')}
                          title="Sort by name"
                        >
                          Name{sortIcon('name')}
                        </th>
                        <th className="cursor-pointer" onClick={() => toggleSort('server')} title="Sort by server">
                          Server{sortIcon('server')}
                        </th>
                        <th className="cursor-pointer" onClick={() => toggleSort('port')} title="Sort by port">
                          Port{sortIcon('port')}
                        </th>
                        <th className="cursor-pointer" onClick={() => toggleSort('node')} title="Sort by node">
                          Node{sortIcon('node')}
                        </th>
                        <th>Group</th>
                        <th>Secret</th>
                        <th className="text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupList.map((proxy) => (
                        <tr key={proxy.id} className="border-b">
                          <td className="py-2 pl-2">
                            <span className="flex items-center gap-2">
                              <span
                                className={
                                  proxy.enabled
                                    ? 'h-2 w-2 shrink-0 rounded-full bg-green-500'
                                    : 'h-2 w-2 shrink-0 rounded-full bg-zinc-400'
                                }
                              />
                              <span className="font-medium">{proxy.name}</span>
                              <Switch checked={!!proxy.enabled} onCheckedChange={(v) => toggleProxyEnabled(proxy, v)} />
                            </span>
                          </td>
                          <td className="text-muted-foreground">{proxy.server}</td>
                          <td>{proxy.port}</td>
                          <td className="text-muted-foreground">{nodeName(proxy.node_id)}</td>
                          <td>
                            {proxy.group_id ? (
                              <Badge variant="secondary" className="text-[10px]">
                                {groups.find((g: { id: number }) => g.id === proxy.group_id)?.name ??
                                  `group ${proxy.group_id}`}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground text-xs">all</span>
                            )}
                          </td>
                          <td>
                            <span className="flex items-center gap-1">
                              <code
                                className="bg-muted max-w-40 truncate rounded px-1.5 py-0.5 text-[11px]"
                                title={revealedSecrets.includes(proxy.id) ? fullSecret(proxy) : 'click reveal'}
                              >
                                {revealedSecrets.includes(proxy.id)
                                  ? fullSecret(proxy)
                                  : `••••••${proxy.secret.slice(-6)}`}
                              </code>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                title="Reveal / hide"
                                onClick={() => toggleReveal(proxy.id)}
                              >
                                {revealedSecrets.includes(proxy.id) ? (
                                  <EyeOff className="h-3.5 w-3.5" />
                                ) : (
                                  <Eye className="h-3.5 w-3.5" />
                                )}
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                title="Copy full secret"
                                onClick={async () => {
                                  await copy(fullSecret(proxy))
                                  toast.success('Secret copied')
                                }}
                              >
                                <Copy className="h-3.5 w-3.5" />
                              </Button>
                            </span>
                          </td>
                          <td>
                            <span className="flex items-center justify-end gap-1 pr-2">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                title="Copy tg:// link"
                                onClick={async () => {
                                  await copy(tgLink(proxy))
                                  toast.success('tg:// link copied')
                                }}
                              >
                                <Copy className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                title="Copy https://t.me link"
                                onClick={async () => {
                                  await copy(httpsLink(proxy))
                                  toast.success('https link copied')
                                }}
                              >
                                <LinkIcon className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                title="QR"
                                onClick={() => setQrLink(tgLink(proxy))}
                              >
                                <QrCode className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                title="Edit (secret, server, port… all editable)"
                                onClick={() => openProxyEdit(proxy)}
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                onClick={() => setDeleteProxyTarget(proxy)}
                              >
                                <Trash2 className="text-destructive h-3.5 w-3.5" />
                              </Button>
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* ------------------------------------------------ client dialog */}
      <Dialog open={clientDialogOpen} onOpenChange={setClientDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingClient ? `Edit client "${editingClient.username}"` : 'Add Proxy Client'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            {!editingClient && (
              <div className="grid gap-1">
                <Label>Username</Label>
                <Input
                  value={clientForm.username}
                  onChange={(e) => setClientForm({ ...clientForm, username: e.target.value })}
                  placeholder="tg-customer-1"
                />
              </div>
            )}
            <div className="grid gap-1">
              <Label>Proxy groups</Label>
              <div className="flex flex-wrap gap-3 rounded-md border p-3">
                {proxyGroups.length === 0 && (
                  <span className="text-muted-foreground text-xs">No proxy group — create one on the Groups page.</span>
                )}
                {proxyGroups.map((g: { id: number; name: string; total_users?: number }) => (
                  <label key={g.id} className="flex cursor-pointer items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={clientForm.groupIds.includes(g.id)}
                      onChange={(e) =>
                        setClientForm((f) => ({
                          ...f,
                          groupIds: e.target.checked ? [...f.groupIds, g.id] : f.groupIds.filter((id) => id !== g.id),
                        }))
                      }
                    />
                    {g.name}
                  </label>
                ))}
              </div>
              <p className="text-muted-foreground text-[11px]">
                Only inbound-less (proxy) groups are listed — clients can never join config groups.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label>Data limit (GB)</Label>
                <Input
                  type="number"
                  min="0"
                  value={clientForm.dataLimitGb}
                  onChange={(e) => setClientForm({ ...clientForm, dataLimitGb: e.target.value })}
                  placeholder="empty = unlimited"
                />
              </div>
              <div className="grid gap-1">
                <Label>{editingClient ? 'Extend expiry by (days)' : 'Expiry (days)'}</Label>
                <Input
                  type="number"
                  min="0"
                  value={clientForm.expireDays}
                  onChange={(e) => setClientForm({ ...clientForm, expireDays: e.target.value })}
                  placeholder="empty = never"
                />
              </div>
            </div>
            <div className="grid gap-1">
              <Label>Usage coefficient</Label>
              <Input
                type="number"
                step="0.1"
                min="0"
                value={clientForm.coefficient}
                onChange={(e) => setClientForm({ ...clientForm, coefficient: e.target.value })}
                placeholder="1"
              />
              <p className="text-muted-foreground text-[11px]">
                Multiplies this client's counted traffic — 2 makes their quota burn twice as fast.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setClientDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submitClient} disabled={createClientMutation.isPending || modifyClientMutation.isPending}>
              {editingClient ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ------------------------------------------------ proxy dialog */}
      <Dialog open={proxyDialogOpen} onOpenChange={setProxyDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingProxy ? 'Edit Telegram Proxy' : 'Add Telegram Proxy'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label>Name</Label>
              <Input value={proxyForm.name} onChange={(e) => setProxyForm({ ...proxyForm, name: e.target.value })} placeholder="main-tg" />
            </div>
            <div className="grid gap-1">
              <Label>Server (IP or domain)</Label>
              <Input value={proxyForm.server} onChange={(e) => setProxyForm({ ...proxyForm, server: e.target.value })} placeholder="5.6.7.8" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label>Port</Label>
                <Input
                  type="number"
                  value={proxyForm.port}
                  onChange={(e) => setProxyForm({ ...proxyForm, port: e.target.value })}
                  placeholder="443"
                />
              </div>
              <div className="grid gap-1">
                <Label>Enabled</Label>
                <div className="flex h-10 items-center">
                  <Switch checked={!!proxyForm.enabled} onCheckedChange={(v) => setProxyForm({ ...proxyForm, enabled: v })} />
                </div>
              </div>
            </div>
            <div className="grid gap-1">
              <Label>Secret</Label>
              <div className="flex gap-2">
                <Input
                  value={proxyForm.secret}
                  onChange={(e) => setProxyForm({ ...proxyForm, secret: e.target.value })}
                  placeholder="ee… (leave empty to auto-generate)"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  title="Generate a new secret"
                  onClick={() => setProxyForm({ ...proxyForm, secret: generateMtprotoSecret() })}
                >
                  <RefreshCcw className="h-4 w-4" />
                </Button>
              </div>
              {editingProxy && proxyForm.secret.trim() && proxyForm.secret.trim() !== editingProxy.secret && (
                <p className="text-amber-500 text-[11px]">
                  The secret changed — links already shared for "{editingProxy.name}" stop working. Share the new
                  tg:// link after saving.
                </p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label>Sponsored channel (optional)</Label>
                <Input
                  value={proxyForm.sponsoredChannel}
                  onChange={(e) => setProxyForm({ ...proxyForm, sponsoredChannel: e.target.value })}
                  placeholder="@mychannel"
                />
              </div>
              <div className="grid gap-1">
                <Label>MTProxybot tag (optional)</Label>
                <Input
                  value={proxyForm.tag}
                  onChange={(e) => setProxyForm({ ...proxyForm, tag: e.target.value })}
                  placeholder="16 hex chars"
                />
              </div>
            </div>
            <div className="grid gap-1">
              <Label>Visible to group (optional — only clients of this group see this proxy)</Label>
              <select
                className="border-input bg-background h-10 rounded-md border px-3 text-sm"
                value={proxyForm.groupId}
                onChange={(e) => setProxyForm({ ...proxyForm, groupId: e.target.value })}
              >
                <option value="">— all clients —</option>
                {groups.map((g: { id: number; name: string; inbound_tags?: string[] | null }) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                    {!g.inbound_tags?.length ? ' (proxy group)' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div className="grid gap-1">
              <Label>Node server hosting this proxy (optional)</Label>
              <select
                className="border-input bg-background h-10 rounded-md border px-3 text-sm"
                value={proxyForm.nodeId}
                onChange={(e) => setProxyForm({ ...proxyForm, nodeId: e.target.value })}
              >
                <option value="">— none —</option>
                {nodes.map((n: { id: number; name: string }) => (
                  <option key={n.id} value={n.id}>
                    {n.name}
                  </option>
                ))}
              </select>
            </div>
            <p className="text-muted-foreground text-xs">
              Get the secret from the server running the proxy (`drvpn install-mtproto` prints it, or `drvpn edit-mtproto`).
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setProxyDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submitProxy} disabled={createProxyMutation.isPending || modifyProxyMutation.isPending}>
              {editingProxy ? 'Save' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* QR dialog */}
      <Dialog open={!!qrLink} onOpenChange={(v) => !v && setQrLink(null)}>
        <DialogContent className="flex flex-col items-center">
          <DialogHeader>
            <DialogTitle>Scan in Telegram</DialogTitle>
          </DialogHeader>
          {qrLink && <QRCodeCanvas value={qrLink} size={220} />}
          <p className="text-muted-foreground break-all text-center text-xs">{qrLink}</p>
        </DialogContent>
      </Dialog>

      {/* delete proxy confirm */}
      <Dialog open={!!deleteProxyTarget} onOpenChange={(v) => !v && setDeleteProxyTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete "{deleteProxyTarget?.name}"?</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">
            Clients will no longer see this Telegram proxy on their subscription page.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteProxyTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeleteProxy} disabled={removeProxyMutation.isPending}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* delete client confirm */}
      <Dialog open={!!deleteClientTarget} onOpenChange={(v) => !v && setDeleteClientTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete client "{deleteClientTarget?.username}"?</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">
            The client and their subscription link will be removed. Their Telegram proxy access stops immediately.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteClientTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDeleteClient} disabled={removeClientMutation.isPending}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
