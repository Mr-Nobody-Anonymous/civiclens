/* Offline-first report queue.

   When submission fails due to connectivity, the report body (and small
   evidence files as base64) is stored in localStorage with a client_key
   (idempotency: the server returns the original report on retried keys, so
   reconnect can never create duplicates). A sync loop drains the queue when
   the browser comes back online. */
import { api, uploadWithProgress } from './api'

export interface QueuedReport {
  client_key: string
  body: Record<string, unknown>
  files: { name: string; type: string; data: string }[]   // base64, small files only
  created_at: string
  status: 'queued' | 'syncing' | 'failed'
  error?: string
}

const KEY = 'cl_offline_queue'
const MAX_OFFLINE_FILE = 8 * 1024 * 1024   // only queue evidence <= 8MB offline

export function getQueue(): QueuedReport[] {
  try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] }
}

function saveQueue(q: QueuedReport[]) {
  localStorage.setItem(KEY, JSON.stringify(q))
  window.dispatchEvent(new CustomEvent('cl-offline-queue', { detail: q.length }))
}

export async function enqueueReport(body: Record<string, unknown>, files: File[]): Promise<QueuedReport> {
  const entry: QueuedReport = {
    client_key: `off-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    body, files: [], created_at: new Date().toISOString(), status: 'queued',
  }
  for (const f of files) {
    if (f.size <= MAX_OFFLINE_FILE) {
      entry.files.push({ name: f.name, type: f.type, data: await fileToB64(f) })
    }
  }
  const q = getQueue()
  q.push(entry)
  saveQueue(q)
  return entry
}

function fileToB64(f: File): Promise<string> {
  return new Promise((res, rej) => {
    const r = new FileReader()
    r.onload = () => res((r.result as string).split(',')[1])
    r.onerror = rej
    r.readAsDataURL(f)
  })
}

function b64ToFile(item: { name: string; type: string; data: string }): File {
  const bin = atob(item.data)
  const arr = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i)
  return new File([arr], item.name, { type: item.type })
}

let syncing = false

/** Drain the queue. Safe to call repeatedly; idempotency keys prevent duplicates. */
export async function syncQueue(onSynced?: (code: string) => void): Promise<number> {
  if (syncing || !navigator.onLine) return 0
  syncing = true
  let synced = 0
  try {
    for (const entry of getQueue()) {
      if (entry.status === 'syncing') continue
      try {
        entry.status = 'syncing'; saveQueue(getQueue().map(e => e.client_key === entry.client_key ? entry : e))
        const rpt = await api.post('/api/reports', { ...entry.body, client_key: entry.client_key })
        for (const fi of entry.files) {
          await uploadWithProgress(`/api/reports/${rpt.id}/media`, b64ToFile(fi), {}, () => {})
        }
        await api.post(`/api/reports/${rpt.id}/finalize`)
        saveQueue(getQueue().filter(e => e.client_key !== entry.client_key))
        synced++
        onSynced?.(rpt.public_code)
      } catch (e) {
        const err = e as { status?: number; message?: string }
        if (err.status && err.status > 0 && err.status !== 429) {
          // real server rejection (validation etc.) — mark failed, keep for user review
          entry.status = 'failed'; entry.error = err.message
        } else {
          entry.status = 'queued'   // network problem — retry next time
        }
        saveQueue(getQueue().map(e => e.client_key === entry.client_key ? entry : e))
      }
    }
  } finally { syncing = false }
  return synced
}

export function removeQueued(client_key: string) {
  saveQueue(getQueue().filter(e => e.client_key !== client_key))
}

/** Install global online/offline listeners + periodic sync. Returns cleanup. */
export function installOfflineSync(onSynced?: (code: string) => void): () => void {
  const onOnline = () => { void syncQueue(onSynced) }
  window.addEventListener('online', onOnline)
  const iv = setInterval(onOnline, 60_000)
  if (navigator.onLine) void syncQueue(onSynced)
  return () => { window.removeEventListener('online', onOnline); clearInterval(iv) }
}
