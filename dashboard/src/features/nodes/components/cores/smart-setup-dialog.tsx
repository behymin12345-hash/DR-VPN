import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Gauge, KeyRound, ShieldCheck, Sparkles, TriangleAlert } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { LoaderButton } from '@/components/ui/loader-button'
import {
  SmartSetupResponse,
  useGetNodes,
  useRunSmartSetup,
} from '@/service/api'

const profileColor = (profile: string) =>
  profile === 'turbo'
    ? 'bg-green-500/15 text-green-500'
    : profile === 'balanced'
      ? 'bg-blue-500/15 text-blue-500'
      : 'bg-amber-500/15 text-amber-500'

export function SmartSetupButton({ canCreate }: { canCreate: boolean }) {
  const [open, setOpen] = useState(false)
  const { data: nodesResp } = useGetNodes()
  const nodes = nodesResp?.nodes ?? []
  const queryClient = useQueryClient()

  const [domain, setDomain] = useState('')
  const [basePort, setBasePort] = useState('443')
  const [nodeId, setNodeId] = useState('')
  const [result, setResult] = useState<SmartSetupResponse | null>(null)

  const setupMutation = useRunSmartSetup()

  const run = async () => {
    if (!domain.trim()) {
      toast.error('Enter your domain first')
      return
    }
    const port = Number(basePort) || 443
    try {
      const res = await setupMutation.mutateAsync({
        data: {
          domain: domain.trim(),
          base_port: port,
          node_id: nodeId ? Number(nodeId) : null,
          include_vmess: null,
        },
      })
      setResult(res)
      queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
      queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
      queryClient.invalidateQueries({ queryKey: ['/api/groups'] })
      queryClient.invalidateQueries({ queryKey: ['/api/hosts'] })
      toast.success(`Smart Setup finished — profile "${res.profile}"`)
    } catch (e: any) {
      const detail = e?.response?._data?.detail || e?.message
      toast.error(typeof detail === 'string' ? detail : 'Smart Setup failed')
    }
  }

  const reset = () => {
    setResult(null)
    setOpen(false)
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} disabled={!canCreate}>
        <Sparkles className="h-4 w-4" /> Smart Setup
      </Button>

      <Dialog open={open} onOpenChange={(v) => (v ? setOpen(true) : reset())}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5" /> Smart Setup — auto-generate a secure stack
            </DialogTitle>
          </DialogHeader>

          {!result ? (
            <div className="grid gap-3 py-2">
              <p className="text-muted-foreground text-xs">
                The engine measures real latency from this panel to your node and to the internet, picks a profile and
                builds a full secure stack — fresh REALITY keys (x25519), WebSocket fallback and SS-2022 — then creates
                the core, group and hosts for you. Everything stays editable afterwards.
              </p>
              <div className="grid gap-1">
                <Label>Domain (points to this server)</Label>
                <Input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="panel.example.com" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1">
                  <Label>Base port (Reality)</Label>
                  <Input type="number" value={basePort} onChange={(e) => setBasePort(e.target.value)} />
                </div>
                <div className="grid gap-1">
                  <Label>Node</Label>
                  <select
                    className="border-input bg-background h-10 rounded-md border px-3 text-sm"
                    value={nodeId}
                    onChange={(e) => setNodeId(e.target.value)}
                  >
                    <option value="">auto (first connected)</option>
                    {nodes.map((n: { id: number; name: string; status: string }) => (
                      <option key={n.id} value={n.id}>
                        {n.name} ({n.status})
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          ) : (
            <div className="grid gap-3 py-2">
              <div className="flex items-center gap-2">
                <Badge className={profileColor(result.profile)}>{result.profile}</Badge>
                <span className="text-muted-foreground text-xs">{result.profile_reason}</span>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div className="bg-muted rounded-md p-3">
                  <p className="text-muted-foreground flex items-center gap-1 text-[11px]">
                    <Gauge className="h-3 w-3" /> Node latency
                  </p>
                  <p className="text-lg font-semibold">
                    {result.node_latency_ms != null ? `${result.node_latency_ms} ms` : '—'}
                  </p>
                </div>
                <div className="bg-muted rounded-md p-3">
                  <p className="text-muted-foreground flex items-center gap-1 text-[11px]">
                    <Gauge className="h-3 w-3" /> Internet latency
                  </p>
                  <p className="text-lg font-semibold">
                    {result.internet_latency_ms != null ? `${result.internet_latency_ms} ms` : '—'}
                  </p>
                </div>
              </div>

              <div className="rounded-md border p-3">
                <p className="mb-1 text-sm font-medium">
                  Core #{result.core_id} "{result.core_name}" · Group "{result.group_name}" · {result.host_count} hosts
                </p>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-muted-foreground text-left">
                      <th className="py-1">Inbound</th>
                      <th>Port</th>
                      <th>Protocol</th>
                      <th>Security</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.inbounds.map((ib) => (
                      <tr key={ib.tag} className="border-t">
                        <td className="py-1 font-medium">{ib.tag}</td>
                        <td>{ib.port}</td>
                        <td>{ib.protocol}</td>
                        <td>
                          {ib.security === 'reality' ? (
                            <Badge className="bg-violet-500/15 text-violet-500">REALITY</Badge>
                          ) : (
                            ib.security
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <ul className="grid gap-1">
                {result.security_notes?.map((note) => (
                  <li key={note} className="flex items-start gap-1.5 text-xs">
                    <ShieldCheck className="text-green-500 mt-0.5 h-3.5 w-3.5 shrink-0" /> {note}
                  </li>
                ))}
                <li className="flex items-start gap-1.5 text-xs">
                  <KeyRound className="text-violet-500 mt-0.5 h-3.5 w-3.5 shrink-0" /> Keys live inside the core config
                  (Nodes → Cores) — users get them automatically through their subscription.
                </li>
              </ul>

              {result.warnings?.map((w) => (
                <p key={w} className="flex items-start gap-1.5 text-xs text-amber-500">
                  <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {w}
                </p>
              ))}

              <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
                <CheckCircle2 className="text-green-500 h-3.5 w-3.5" /> Assign users to group "{result.group_name}"
                and their subscription instantly serves all four protocols.
              </p>
            </div>
          )}

          <DialogFooter>
            {result ? (
              <>
                <Button variant="outline" onClick={() => setResult(null)}>
                  Run again
                </Button>
                <Button onClick={reset}>Done</Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={reset}>
                  Cancel
                </Button>
                <LoaderButton onClick={run} isLoading={setupMutation.isPending} loadingText="Measuring & building…">
                  <Sparkles className="h-4 w-4" /> Build it
                </LoaderButton>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
