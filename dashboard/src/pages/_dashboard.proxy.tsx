import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Copy, Plus, QrCode, Trash2 } from 'lucide-react'
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
} from '@/service/api'
import { useClipboard } from '@/hooks/use-clipboard'

const tgLink = (p: { server: string; port: number; secret: string }) =>
  `tg://proxy?server=${p.server}&port=${p.port}&secret=${p.secret}`
const httpsLink = (p: { server: string; port: number; secret: string }) =>
  `https://t.me/proxy?server=${p.server}&port=${p.port}&secret=${p.secret}`

interface ProxyFormValue {
  name: string
  server: string
  port: string
  secret: string
  enabled: boolean
}

const emptyForm: ProxyFormValue = { name: '', server: '', port: '443', secret: '', enabled: true }

export default function ProxyPage() {
  const { data: proxies = [], isLoading } = useGetMtprotoProxies()
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
    })
    setDialogOpen(true)
  }

  const submit = async () => {
    const payload = {
      name: form.name.trim(),
      server: form.server.trim(),
      port: Number(form.port),
      secret: form.secret.trim(),
      enabled: form.enabled,
    }
    if (!payload.name || !payload.server || !payload.secret || !payload.port) {
      toast.error('Please fill in all fields')
      return
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
                  </div>
                  <div className="flex items-center gap-1">
                    <Switch checked={!!proxy.enabled} onCheckedChange={(v) => toggleEnabled(proxy, v)} />
                    <Button variant="ghost" size="icon" onClick={() => openEdit(proxy)}>
                      <Plus className="h-4 w-4 rotate-45" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setQrLink(tgLink(proxy))}>
                      <QrCode className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(proxy)}>
                      <Trash2 className="text-destructive h-4 w-4" />
                    </Button>
                  </div>
                </div>
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
              <Input value={form.secret} onChange={(e) => setForm({ ...form, secret: e.target.value })} placeholder="ee…" />
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
