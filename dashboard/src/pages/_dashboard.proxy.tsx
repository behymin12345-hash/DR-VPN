import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  Ban,
  CheckCircle2,
  Copy,
  ExternalLink,
  Pencil,
  QrCode,
  RefreshCcw,
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
          <div className="mb-3 flex items-center gap-2">
            <Button onClick={openProxyCreate} size="sm">
              <QrCode className="h-4 w-4" /> Add Proxy
            </Button>
            <p className="text-muted-foreground text-xs">
              Enabled proxies appear on the subscription page of clients whose group matches.
            </p>
          </div>

          {proxiesLoading ? (
            <p className="text-muted-foreground p-4 text-sm">Loading…</p>
          ) : proxies.length === 0 ? (
            <Card>
              <CardContent className="text-muted-foreground p-10 text-center text-sm">
                No Telegram proxies yet — click "Add Proxy" to create one, then share the link with your clients.
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {proxies.map((proxy) => (
                <Card key={proxy.id}>
                  <CardContent className="flex flex-col gap-2 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <span
                          className={
                            proxy.enabled
                              ? 'h-2 w-2 shrink-0 rounded-full bg-green-500'
                              : 'h-2 w-2 shrink-0 rounded-full bg-zinc-400'
                          }
                        />
                        <span className="truncate font-medium">{proxy.name}</span>
                        <span className="text-muted-foreground truncate text-xs">
                          {proxy.server}:{proxy.port}
                        </span>
                        {proxy.node_id && (
                          <span className="bg-muted rounded px-1.5 py-0.5 text-[10px]">node #{proxy.node_id}</span>
                        )}
                        {proxy.group_id && (
                          <Badge variant="secondary" className="text-[10px]">
                            {groups.find((g: { id: number }) => g.id === proxy.group_id)?.name ?? `group ${proxy.group_id}`}
                          </Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        <Switch checked={!!proxy.enabled} onCheckedChange={(v) => toggleProxyEnabled(proxy, v)} />
                        <Button variant="ghost" size="icon" title="Edit" onClick={() => openProxyEdit(proxy)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => setQrLink(tgLink(proxy))}>
                          <QrCode className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" onClick={() => setDeleteProxyTarget(proxy)}>
                          <Trash2 className="text-destructive h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    {proxy.sponsored_channel && (
                      <p className="text-muted-foreground truncate text-xs">Sponsored: {proxy.sponsored_channel}</p>
                    )}
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1"
                        onClick={async () => {
                          await copy(tgLink(proxy))
                          toast.success('tg:// link copied')
                        }}
                      >
                        <Copy className="h-3 w-3" /> tg:// link
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="flex-1"
                        onClick={async () => {
                          await copy(httpsLink(proxy))
                          toast.success('https link copied')
                        }}
                      >
                        <Copy className="h-3 w-3" /> https link
                      </Button>
                    </div>
                  </CardContent>
                </Card>
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
