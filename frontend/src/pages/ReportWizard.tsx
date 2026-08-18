/* Multi-step report submission: Evidence -> Location -> Describe -> Submit. */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Camera, CheckCircle2, ChevronLeft, ChevronRight, Clapperboard, FileVideo, Loader2, LocateFixed, MapPin, Sparkles, Square, Trash2, Upload, Video } from 'lucide-react'
import { api, reverseGeocode, uploadWithProgress, ApiError } from '../lib/api'
import { useApp } from '../lib/store'
import { useI18n } from '../lib/i18n'
import IssueMap from '../components/IssueMap'
import { CATEGORY_ICONS, type Report } from '../lib/types'
import { SeverityBadge, StatusBadge } from '../components/ui'

type Evidence = { file: File; kind: 'video' | 'image'; preview: string }

const STEPS = ['evidence', 'location', 'describe', 'review'] as const

export default function ReportWizard() {
  const { user, meta, toast } = useApp()
  const { t } = useI18n()
  const [step, setStep] = useState(0)

  // step 1
  const [evidence, setEvidence] = useState<Evidence[]>([])
  const [recording, setRecording] = useState(false)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const videoPreviewRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)

  // step 2
  const [pos, setPos] = useState<[number, number] | null>(null)
  const [address, setAddress] = useState('')
  const [city, setCity] = useState('')
  const [locating, setLocating] = useState(false)

  // step 3
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [category, setCategory] = useState('')
  const [comments, setComments] = useState('')
  const [captcha] = useState(() => ({ a: 2 + Math.floor(Math.random() * 7), b: 1 + Math.floor(Math.random() * 8) }))
  const [captchaAns, setCaptchaAns] = useState('')

  // submit
  const createdRef = useRef<Report | null>(null)      // created report survives upload retries
  const uploadedRef = useRef<Set<number>>(new Set())  // successfully uploaded evidence indexes
  const [submitting, setSubmitting] = useState(false)
  const [progress, setProgress] = useState<Record<number, number>>({})
  const [done, setDone] = useState<Report | null>(null)
  const [analysis, setAnalysis] = useState<Report['ai']>(null)
  const [doneStatus, setDoneStatus] = useState('submitted')

  useEffect(() => { if (meta && !city) setCity(meta.cities[0]) }, [meta]) // eslint-disable-line react-hooks/exhaustive-deps

  // Don't lose an in-flight submission if the user accidentally navigates away.
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => { if (submitting) { e.preventDefault(); e.returnValue = '' } }
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [submitting])

  // poll AI analysis after submission
  useEffect(() => {
    if (!done) return
    const iv = setInterval(async () => {
      try {
        const d = await api.get(`/api/reports/${done.id}/analysis`)
        setDoneStatus(d.status)
        if (d.analysis) { setAnalysis(d.analysis); clearInterval(iv) }
      } catch { /* keep polling */ }
    }, 2500)
    return () => clearInterval(iv)
  }, [done])

  const maxVideo = meta?.max_video_mb ?? 100
  const maxImage = meta?.max_image_mb ?? 10

  function addFiles(files: FileList | File[]) {
    for (const f of Array.from(files)) {
      const isVideo = f.type.startsWith('video/')
      const isImage = f.type.startsWith('image/')
      if (!isVideo && !isImage) { toast('error', `Unsupported file type: ${f.type || f.name}`); continue }
      const limit = (isVideo ? maxVideo : maxImage) * 1024 * 1024
      if (f.size > limit) { toast('error', `${f.name} is too large (max ${isVideo ? maxVideo : maxImage} MB)`); continue }
      setEvidence(ev => [...ev, { file: f, kind: isVideo ? 'video' : 'image', preview: URL.createObjectURL(f) }])
    }
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: true })
      streamRef.current = stream
      if (videoPreviewRef.current) { videoPreviewRef.current.srcObject = stream; videoPreviewRef.current.play() }
      const mime = MediaRecorder.isTypeSupported('video/webm') ? 'video/webm' : 'video/mp4'
      const rec = new MediaRecorder(stream, { mimeType: mime })
      chunksRef.current = []
      rec.ondataavailable = e => chunksRef.current.push(e.data)
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mime })
        const file = new File([blob], `recording-${Date.now()}.${mime.includes('webm') ? 'webm' : 'mp4'}`, { type: mime })
        addFiles([file])
        stream.getTracks().forEach(tr => tr.stop())
        streamRef.current = null
      }
      rec.start()
      recorderRef.current = rec
      setRecording(true)
    } catch {
      toast('error', 'Camera access denied or unavailable — you can upload a video instead.')
    }
  }
  function stopRecording() { recorderRef.current?.stop(); setRecording(false) }

  function useMyLocation() {
    if (!navigator.geolocation) { toast('error', 'Geolocation is not supported by this browser'); return }
    setLocating(true)
    navigator.geolocation.getCurrentPosition(async p => {
      const { latitude, longitude } = p.coords
      setPos([latitude, longitude])
      const addr = await reverseGeocode(latitude, longitude)
      if (addr) setAddress(addr)
      setLocating(false)
    }, () => { setLocating(false); toast('error', 'Location permission denied — tap the map to set the location manually.') },
      { enableHighAccuracy: true, timeout: 10000 })
  }

  async function pick(lat: number, lng: number) {
    setPos([lat, lng])
    const addr = await reverseGeocode(lat, lng)
    if (addr) setAddress(addr)
  }

  const canNext = [
    true,                                    // evidence optional but encouraged
    pos !== null,
    title.trim().length >= 4 && desc.trim().length >= 10 && (user ? true : captchaAns !== ''),
  ]

  async function submit() {
    setSubmitting(true)
    try {
      const body: Record<string, unknown> = {
        title: title.trim(), description: desc.trim(), comments: comments || undefined,
        category: category || undefined, city, latitude: pos?.[0], longitude: pos?.[1],
        address: address || undefined,
      }
      if (!user) { body.captcha_a = captcha.a; body.captcha_b = captcha.b; body.captcha_answer = parseInt(captchaAns || '0', 10) }
      // create the report first — from here on it exists server-side and is never lost
      const rpt: Report = createdRef.current ?? await api.post('/api/reports', body)
      createdRef.current = rpt

      let uploadFailures = 0
      for (let i = 0; i < evidence.length; i++) {
        if (uploadedRef.current.has(i)) continue   // retry submits only what's missing
        try {
          await uploadWithProgress(`/api/reports/${rpt.id}/media`, evidence[i].file, {}, pct =>
            setProgress(p => ({ ...p, [i]: pct })))
          uploadedRef.current.add(i)
        } catch (err) {
          uploadFailures++
          toast('error', `${evidence[i].file.name}: ${(err as Error).message}`)
        }
      }
      if (uploadFailures > 0) {
        toast('info', 'Some evidence failed to upload — press Submit again to retry just those files.')
        setSubmitting(false)
        return
      }
      await api.post(`/api/reports/${rpt.id}/finalize`)
      setDone(rpt)
      toast('success', `Report ${rpt.public_code} submitted!`)
      if (rpt.possible_duplicate) toast('info', `Note: this looks similar to existing report ${rpt.duplicate_of_code}. A reviewer may link them — nothing is deleted.`)
    } catch (e) {
      toast('error', e instanceof ApiError ? e.message : 'Submission failed — please try again')
    } finally {
      setSubmitting(false)
    }
  }

  /* ---------------- confirmation screen ---------------- */
  if (done) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <div className="card overflow-hidden animate-fade-up">
          <div className="eth-strip h-1" />
          <div className="p-7 text-center">
            <div className="mx-auto grid size-16 place-items-center rounded-full bg-emerald-100 dark:bg-emerald-500/15">
              <CheckCircle2 className="size-9 text-emerald-600 dark:text-emerald-400" />
            </div>
            <h1 className="mt-4 text-2xl font-extrabold">Report submitted!</h1>
            <p className="mt-1 text-gray-500 dark:text-gray-400">Keep this ID to track your report.</p>
            <p className="mt-4 inline-block rounded-xl bg-gray-100 px-5 py-2.5 font-mono text-xl font-bold tracking-wider dark:bg-white/10">{done.public_code}</p>

            <div className="mt-6 grid gap-3 text-left sm:grid-cols-2">
              <div className="card p-4"><p className="text-xs text-gray-500">Status</p><div className="mt-1.5"><StatusBadge status={analysis ? doneStatus : 'ai_analysis'} size="lg" /></div></div>
              <div className="card p-4"><p className="text-xs text-gray-500">Location</p><p className="mt-1.5 flex items-center gap-1.5 text-sm font-medium"><MapPin className="size-4 text-brand-600" />{address ? address.split(',').slice(0, 2).join(',') : `${pos?.[0].toFixed(4)}, ${pos?.[1].toFixed(4)}`}</p></div>
              <div className="card p-4 sm:col-span-2"><p className="text-xs text-gray-500">Evidence</p>
                <p className="mt-1.5 text-sm font-medium">{evidence.length === 0 ? 'No media attached' : `${evidence.filter(e => e.kind === 'video').length} video(s), ${evidence.filter(e => e.kind === 'image').length} photo(s) uploaded securely`}</p></div>
            </div>

            {/* AI progress / result */}
            <div className="card mt-4 p-5 text-left">
              {!analysis ? (
                <div className="flex items-center gap-4">
                  <div className="relative">
                    <Sparkles className="size-8 text-violet-500 animate-pulse-soft" />
                  </div>
                  <div className="flex-1">
                    <p className="font-semibold">AI analysis in progress…</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Extracting video frames and classifying the issue with the local model.</p>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-200 dark:bg-white/10">
                      <div className="h-full w-1/3 rounded-full bg-gradient-to-r from-brand-500 via-et-yellow to-brand-500 animate-shimmer" style={{ backgroundSize: '400px 100%', width: '100%' }} />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="animate-fade-up">
                  <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-violet-600 dark:text-violet-300"><Sparkles className="size-4" />{t('ai_classification')}</p>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-sm">
                    <div><p className="text-xs text-gray-500">Category</p><p className="font-semibold">{CATEGORY_ICONS[analysis.category ?? 'Other']} {analysis.category}</p></div>
                    <div><p className="text-xs text-gray-500">Issue</p><p className="font-semibold">{analysis.issue_type}</p></div>
                    <div><p className="text-xs text-gray-500">{t('severity')}</p><SeverityBadge sev={analysis.severity} /></div>
                    <div><p className="text-xs text-gray-500">{t('confidence')}</p><p className="font-semibold">{Math.round((analysis.confidence ?? 0) * 100)}%</p></div>
                    {analysis.responsible_organization && <div className="col-span-2"><p className="text-xs text-gray-500">Recommended organization</p><p className="font-semibold">{analysis.responsible_organization}</p></div>}
                  </div>
                  <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-400/10 dark:text-amber-300">{t('ai_disclaimer')}</p>
                </div>
              )}
            </div>

            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Link to={`/reports/${done.id}`} className="btn-primary">View report<ChevronRight className="size-4" /></Link>
              <Link to="/reports" className="btn-secondary">{t('explore')}</Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  /* ---------------- wizard ---------------- */
  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-extrabold md:text-3xl">{t('report_issue')}</h1>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">You don't need to know which office is responsible — our AI figures that out.</p>

      {/* stepper */}
      <ol className="mt-6 flex items-center gap-1.5" aria-label="Progress">
        {STEPS.map((s, i) => (
          <li key={s} className="flex flex-1 flex-col items-center gap-1.5">
            <div className={`h-1.5 w-full rounded-full transition-colors ${i <= step ? 'bg-brand-600' : 'bg-gray-200 dark:bg-white/10'}`} />
            <span className={`text-[11px] font-semibold ${i === step ? 'text-brand-700 dark:text-brand-300' : 'text-gray-400'}`}>{t(s === 'evidence' ? 'evidence' : s === 'location' ? 'location' : s === 'describe' ? 'describe' : 'review')}</span>
          </li>
        ))}
      </ol>

      <div className="card mt-5 p-6 animate-fade-up" key={step}>
        {step === 0 && (
          <div className="space-y-5">
            <div className="flex items-center gap-3"><Video className="size-6 text-brand-600" /><div>
              <h2 className="font-bold">Capture evidence</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">A short video helps organizations understand the problem fast. Photos work too.</p>
            </div></div>

            {recording && (
              <div className="overflow-hidden rounded-2xl border-2 border-et-red">
                <video ref={videoPreviewRef} muted playsInline className="max-h-72 w-full bg-black object-cover" />
                <div className="flex items-center justify-between bg-black px-4 py-3">
                  <span className="flex items-center gap-2 text-sm font-semibold text-white"><span className="size-2.5 animate-pulse rounded-full bg-et-red" />Recording…</span>
                  <button onClick={stopRecording} className="btn-danger !py-1.5"><Square className="size-4" />Stop</button>
                </div>
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-3">
              <button onClick={recording ? stopRecording : startRecording} className="btn-secondary flex-col !items-center gap-2 !rounded-2xl !py-5">
                <Clapperboard className="size-6 text-et-red" /><span>{t('record_video')}</span>
              </button>
              <label className="btn-secondary flex-col !items-center gap-2 !rounded-2xl !py-5 cursor-pointer">
                <FileVideo className="size-6 text-brand-600" /><span>{t('upload_video')}</span>
                <input type="file" accept="video/mp4,video/webm,video/quicktime" className="sr-only" onChange={e => e.target.files && addFiles(e.target.files)} />
              </label>
              <label className="btn-secondary flex-col !items-center gap-2 !rounded-2xl !py-5 cursor-pointer">
                <Camera className="size-6 text-et-yellow" /><span>{t('add_photos')}</span>
                <input type="file" accept="image/jpeg,image/png,image/webp" multiple className="sr-only" onChange={e => e.target.files && addFiles(e.target.files)} />
              </label>
            </div>
            <p className="text-xs text-gray-400">Video up to {maxVideo} MB (MP4/WebM/MOV) · Photos up to {maxImage} MB (JPG/PNG/WebP)</p>

            {evidence.length > 0 && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {evidence.map((ev, i) => (
                  <div key={i} className="group relative overflow-hidden rounded-xl border border-gray-200 dark:border-white/10">
                    {ev.kind === 'video'
                      ? <video src={ev.preview} className="h-28 w-full object-cover" muted />
                      : <img src={ev.preview} alt="" className="h-28 w-full object-cover" />}
                    <span className="absolute left-1.5 top-1.5 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] font-bold text-white">{ev.kind.toUpperCase()}</span>
                    <button aria-label="Remove" onClick={() => setEvidence(list => list.filter((_, j) => j !== i))}
                      className="absolute right-1.5 top-1.5 rounded-md bg-black/60 p-1 text-white hover:bg-et-red"><Trash2 className="size-3.5" /></button>
                    {submitting && <div className="absolute inset-x-0 bottom-0 h-1.5 bg-black/30"><div className="h-full bg-brand-500 transition-all" style={{ width: `${progress[i] ?? 0}%` }} /></div>}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <div className="flex items-center gap-3"><MapPin className="size-6 text-brand-600" /><div>
              <h2 className="font-bold">Where is the problem?</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400">We only use your location to place this report on the map — with your permission.</p>
            </div></div>
            <div className="flex flex-wrap items-center gap-3">
              <button onClick={useMyLocation} className="btn-primary" disabled={locating}>
                {locating ? <Loader2 className="size-4 animate-spin" /> : <LocateFixed className="size-4" />}{t('use_my_location')}
              </button>
              <span className="text-sm text-gray-500 dark:text-gray-400">{t('tap_map')}</span>
            </div>
            <IssueMap onPick={pick} picked={pos} className="h-72 md:h-80"
              center={meta ? [meta.default_center.lat, meta.default_center.lng] : undefined} />
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label" htmlFor="city">City</label>
                <select id="city" className="input" value={city} onChange={e => setCity(e.target.value)}>
                  {(meta?.cities ?? ['Addis Ababa']).map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="addr">Address / landmark</label>
                <input id="addr" className="input" value={address} onChange={e => setAddress(e.target.value)} placeholder="e.g. Bole Road, near Edna Mall" />
              </div>
            </div>
            {pos && <p className="text-xs font-mono text-gray-400">📍 {pos[0].toFixed(5)}, {pos[1].toFixed(5)}</p>}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div>
              <label className="label" htmlFor="title">{t('title')} *</label>
              <input id="title" className="input" value={title} onChange={e => setTitle(e.target.value)} maxLength={200}
                placeholder="e.g. Deep pothole on the main road" />
            </div>
            <div>
              <label className="label" htmlFor="desc">{t('description')} *</label>
              <textarea id="desc" className="input min-h-32" value={desc} onChange={e => setDesc(e.target.value)} maxLength={5000}
                placeholder="Describe what you see, how long it has been there, and who is affected…" />
              <p className="mt-1 text-right text-xs text-gray-400">{desc.length}/5000</p>
            </div>
            <div>
              <span className="label">{t('category_opt')}</span>
              <div className="flex flex-wrap gap-2">
                {(meta?.categories ?? []).map(c => (
                  <button key={c} type="button" onClick={() => setCategory(category === c ? '' : c)}
                    className={`rounded-full border px-3.5 py-1.5 text-sm font-medium transition ${category === c ? 'border-brand-600 bg-brand-600 text-white shadow-md shadow-brand-600/25' : 'border-gray-300 bg-white text-gray-700 hover:border-brand-400 dark:border-white/15 dark:bg-white/5 dark:text-gray-200'}`}>
                    {CATEGORY_ICONS[c]} {c}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="label" htmlFor="cmts">{t('comments_opt')}</label>
              <textarea id="cmts" className="input" value={comments} onChange={e => setComments(e.target.value)} maxLength={2000} />
            </div>
            {!user && (
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-white/10 dark:bg-white/5">
                <label className="label" htmlFor="captcha">Quick check: what is {captcha.a} + {captcha.b}? *</label>
                <input id="captcha" inputMode="numeric" className="input max-w-32" value={captchaAns} onChange={e => setCaptchaAns(e.target.value)} />
                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">You're reporting anonymously. <Link className="font-semibold text-brand-700 dark:text-brand-300 hover:underline" to="/login">Sign in</Link> to track your reports and get notified.</p>
              </div>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <h2 className="font-bold">Review & submit</h2>
            <dl className="space-y-3 text-sm">
              <div className="flex justify-between gap-4"><dt className="text-gray-500">{t('title')}</dt><dd className="text-right font-semibold">{title}</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-gray-500">Category</dt><dd className="font-semibold">{category || 'AI will decide'}</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-gray-500">{t('location')}</dt><dd className="text-right font-semibold">{address ? address.split(',').slice(0, 2).join(',') : pos ? `${pos[0].toFixed(4)}, ${pos[1].toFixed(4)}` : '—'} · {city}</dd></div>
              <div className="flex justify-between gap-4"><dt className="text-gray-500">{t('evidence')}</dt><dd className="font-semibold">{evidence.length} file(s)</dd></div>
            </dl>
            <div className="rounded-xl bg-brand-50 p-4 text-xs text-brand-900 dark:bg-brand-400/10 dark:text-brand-200">
              By submitting, you agree your video/photos will be reviewed by our AI and the responsible organization to fix this issue.
              Your name and contact details are <strong>never shown publicly</strong>. See the <Link to="/privacy" className="font-bold underline">privacy policy</Link>.
            </div>
            {submitting && evidence.length > 0 && (
              <div className="space-y-2">
                {evidence.map((ev, i) => (
                  <div key={i}>
                    <div className="flex justify-between text-xs"><span className="truncate">{ev.file.name}</span><span>{progress[i] ?? 0}%</span></div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-white/10">
                      <div className="h-full rounded-full bg-brand-600 transition-all duration-200" style={{ width: `${progress[i] ?? 0}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="mt-7 flex items-center justify-between">
          <button className="btn-secondary" onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0 || submitting}>
            <ChevronLeft className="size-4" />{t('back')}
          </button>
          {step < 3 ? (
            <button className="btn-primary" onClick={() => setStep(s => s + 1)} disabled={!canNext[step]}>
              {t('next')}<ChevronRight className="size-4" />
            </button>
          ) : (
            <button className="btn-primary !px-8" onClick={submit} disabled={submitting}>
              {submitting ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />}{t('submit_report')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
