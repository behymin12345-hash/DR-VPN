import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Copy, Pencil, QrCode, RefreshCcw, Trash2 } from 'lucide-react'
import { QRCodeCanvas } from 'qrcode.react'
import { toast } from 'sonner'

import PageHeader from '@/components/layout/page-header'
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
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import {
  MtprotoProxyResponse,
  useCreateMtprotoProxy,
  useGetMtprotoProxies,
  getGetMtprotoProxiesQueryKey,
  useModifyMtprotoProxy,
  useRemoveMtprotoProxy,
  useGetNodes,
} from '@/service/api'
import { useClipboard } from '@/hooks/use-clipboard'

const generateMtprotoSecret = () => {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

const fullSecret = (p: { secret: string; tag?: string | null }) => 
  p.tag ? `dd${p.tag}${p.secret}` : p.secret
const tgLink = (p: { server: string; port: number; secret: string; tag?: string | null }) =>
  `tg://proxy?server=${p.server}&port=${p.port}&secret=${fullSecret(p)}`
const httpsLink = (p: { server: string; port: number; secret: string; tag?: string | null }) =>
  `https://t.me/proxy?server=${p.server}&port=${p.port}&secret=${fullSecret(p)}`

interface ProxyFormValue {
  name: string
  server: string
  port: string
  secret: string
  enabled: boolean
  sponsoredChannel: string
  tag: string
  nodeId: string
}

const emptyForm: ProxyFormValue = {
  name: '',
  server: '',
  port: '443',
  secret: '',
  enabled: true,
  sponsoredChannel: '',
  tag: '',
  nodeId: '',
}

export default function ProxyPage() {
  const { data: proxies = [], isLoading } = useGetMtprotoProxies()
  const { data: nodesResp } = useGetNodes()
  const nodes = nodesResp?.nodes ?? []
  const queryClient = useQueryClient()
  const { copy } = useClipboard()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<MtprotoProxyResponse | null>(null)
  const [form, setForm] = useState<ProxyFormValue>(emptyForm)
  const [qrLink, setQrLink] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<MtprotoProxyResponse | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: getGetMtprotoProxiesQueryKey() })

  const createMutation = useCreateMtprotoProxy()
  const modifyMutation = useModifyMtprotoProxy()
  const removeMutation = useRemoveMtprotoProxy()

  const openCreate = () => {
    setEditing(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  const openEdit = (proxy: MtprotoProxyResponse) => {
    setEditing(proxy)
    setForm({
      name: proxy.name,
      server: proxy.server,
      port: String(proxy.port),
      secret: proxy.secret,
      enabled: !!proxy.enabled,
      sponsoredChannel: proxy.sponsored_channel ?? '',
      tag: proxy.tag ?? '',
      nodeId: proxy.node_id ? String(proxy.node_id) : '',
    })
    setDialogOpen(true)
  }

  const submit = async () => {
    const payload = {
      name: form.name.trim(),
      server: form.server.trim(),
      port: Number(form.port),
      secret: form.secret.trim() || generateMtprotoSecret(),
      enabled: form.enabled,
      sponsored_channel: form.sponsoredChannel.trim() || null,
      tag: form.tag.trim() || null,
      node_id: form.nodeId ? Number(form.nodeId) : null,
    }
    if (!payload.name || !payload.server || !payload.port) {
      toast.error('Name, server and port are required')
      return
    }
    if (!form.secret.trim()) {
      setForm(f => ({ ...f, secret: payload.secret }))
      toast.success('Secret was generated automatically — it is now on the card')
    }
    try {
      if (editing) {
        await modifyMutation.mutateAsync({ proxyId: editing.id, data: payload })
        toast.success('Proxy updated')
      } else {
        await createMutation.mutateAsync({ data: payload })
        toast.success('Proxy created')
      }
      setDialogOpen(false)
      invalidate()
    } catch {
      toast.error('Failed — the name may already exist')
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    try {
      await removeMutation.mutateAsync({ proxyId: deleteTarget.id })
      toast.success('Proxy deleted')
      setDeleteTarget(null)
      invalidate()
    } catch {
      toast.error('Failed to delete')
    }
  }

  const toggleEnabled = async (proxy: MtprotoProxyResponse, enabled: boolean) => {
    try {
      await modifyMutation.mutateAsync({
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
      invalidate()
    } catch {
      toast.error('Failed to update')
    }
  }

  return (
    <div className="w-full flex-col p-4">
      <PageHeader
        title="Telegram Proxy"
        description="Manage MTProto proxies and share them with your users — enabled proxies appear on every user's subscription page"
        buttonText="Add Proxy"
        onButtonClick={openCreate}
      />
      <Separator className="mb-4" />

      {isLoading ? (
        <p className="text-muted-foreground p-4 text-sm">Loading…</p>
      ) : proxies.length === 0 ? (
        <Card>
          <CardContent className="text-muted-foreground p-10 text-center text-sm">
            No Telegram proxies yet — click "Add Proxy" to create one, then share the link with your users.
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
                        proxy.enabled ? 'h-2 w-2 shrink-0 rounded-full bg-green-500' : 'h-2 w-2 shrink-0 rounded-full bg-zinc-400'
                      }
                    />
                    <span className="truncate font-medium">{proxy.name}</span>
                    <span className="text-muted-foreground truncate text-xs">
                      {proxy.server}:{proxy.port}
                    </span>
                    {proxy.node_id && (
                      <span className="bg-muted rounded px-1.5 py-0.5 text-[10px]">
                        node #{proxy.node_id}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <Switch checked={!!proxy.enabled} onCheckedChange={(v) => toggleEnabled(proxy, v)} />
                    <Button variant="ghost" size="icon" title="Edit" onClick={() => openEdit(proxy)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setQrLink(tgLink(proxy))}>
                      <QrCode className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(proxy)}>
                      <Trash2 className="text-destructive h-4 w-4" />
                    </Button>
                  </div>
                </div>
                {proxy.sponsored_channel && (
                  <p className="text-muted-foreground truncate text-xs">
                    Sponsored: {proxy.sponsored_channel}
                  </p>
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

      {/* create / edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Telegram Proxy' : 'Add Telegram Proxy'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label>Name</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="main-tg" />
            </div>
            <div className="grid gap-1">
              <Label>Server (IP or domain)</Label>
              <Input value={form.server} onChange={(e) => setForm({ ...form, server: e.target.value })} placeholder="5.6.7.8" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label>Port</Label>
                <Input
                  type="number"
                  value={form.port}
                  onChange={(e) => setForm({ ...form, port: e.target.value })}
                  placeholder="443"
                />
              </div>
              <div className="grid gap-1">
                <Label>Enabled</Label>
                <div className="flex h-10 items-center">
                  <Switch checked={!!form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} />
                </div>
              </div>
            </div>
            <div className="grid gap-1">
              <Label>Secret</Label>
              <div className="flex gap-2">
                <Input value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} placeholder="ee… (leave empty to auto-generate)" />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  title="Generate a new secret"
                  onClick={() => setForm({ ...form, secret: generateMtprotoSecret() })}
                >
                  <RefreshCcw className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1">
                <Label>Sponsored channel (optional)</Label>
                <Input
                  value={form.sponsoredChannel}
                  onChange={(e) => setForm({ ...form, sponsoredChannel: e.target.value })}
                  placeholder="@mychannel"
                />
              </div>
              <div className="grid gap-1">
                <Label>MTProxybot tag (optional)</Label>
                <Input
                  value={form.tag}
                  onChange={(e) => setForm({ ...form, tag: e.target.value })}
                  placeholder="16 hex chars"
                />
              </div>
            </div>
            <div className="grid gap-1">
              <Label>Node server hosting this proxy (optional)</Label>
              <select
                className="border-input bg-background h-10 rounded-md border px-3 text-sm"
                value={form.nodeId}
                onChange={(e) => setForm({ ...form, nodeId: e.target.value })}
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
            <Button variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submit} disabled={createMutation.isPending || modifyMutation.isPending}>
              {editing ? 'Save' : 'Create'}
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

      {/* delete confirm */}
      <Dialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete "{deleteTarget?.name}"?</DialogTitle>
          </DialogHeader>
          <p className="text-muted-foreground text-sm">
            Users will no longer see this Telegram proxy on their subscription page.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={removeMutation.isPending}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
