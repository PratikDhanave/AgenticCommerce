import { useCallback, useEffect, useRef, useState } from 'react'

export type Speaker = 'shopper_agent' | 'merchant_agent' | 'human'

/** Spoken-intent commands the buyer can issue with the mic. */
export type Intent =
  | { t: 'act'; act: string }
  | { t: 'run' }
  | { t: 'approve' }
  | { t: 'decline' }
  | { t: 'reset' }
  | { t: 'stop' }
  | { t: 'unknown'; text: string }

/* ---------------------------------------------------------------- voices */

/** macOS ships ~20 joke voices that are indistinguishable from real ones by
 *  metadata alone. Picking "Boing" to read out a payment refusal on stage is
 *  not a recoverable mistake, so they are excluded by name. */
const NOVELTY = new RegExp([
  'Albert', 'Bad News', 'Bahh', 'Bells', 'Boing', 'Bubbles', 'Cellos',
  'Deranged', 'Fred', 'Good News', 'Grandma', 'Grandpa', 'Hysterical',
  'Jester', 'Junior', 'Kathy', 'Organ', 'Princess', 'Ralph', 'Superstar',
  'Trinoids', 'Whisper', 'Wobble', 'Zarvox', 'Bubbles', 'Rocko', 'Shelley',
].join('|'), 'i')

/** Voices that synthesise on-device. Chrome's "Google …" voices round-trip to
 *  a server, which is exactly what we cannot rely on at the venue. */
function localEnglish(all: SpeechSynthesisVoice[]): SpeechSynthesisVoice[] {
  const en = all.filter(v => /^en(-|_|$)/i.test(v.lang) && !NOVELTY.test(v.name))
  const local = en.filter(v => v.localService)
  return local.length ? local : en
}

/** Pick three voices that sound clearly different from each other, so the
 *  room can tell who is talking without reading the screen. */
function assign(all: SpeechSynthesisVoice[]): Record<Speaker, SpeechSynthesisVoice | null> {
  const pool = localEnglish(all)
  const taken = new Set<string>()

  const pick = (prefs: RegExp[]): SpeechSynthesisVoice | null => {
    for (const re of prefs) {
      const hit = pool.find(v => !taken.has(v.name) && re.test(v.name + ' ' + v.lang))
      if (hit) { taken.add(hit.name); return hit }
    }
    const any = pool.find(v => !taken.has(v.name))
    if (any) { taken.add(any.name); return any }
    return pool[0] ?? null
  }

  return {
    // Buyer's agent: Indian English first, it is shopping in Pune.
    shopper_agent: pick([/Veena|Rishi|Sangeeta|Isha/i, /en[-_]IN/i, /Samantha|Ava/i]),
    // Store's agent: a different timbre so A2A turns are audible as a handoff.
    merchant_agent: pick([/Daniel|Alex|Oliver|Tom|Aaron/i, /en[-_]GB/i, /Reed|Eddy/i]),
    // The buyer, for the scripted mid-act lines.
    human: pick([/Samantha|Karen|Moira|Tessa|Fiona|Serena/i, /en[-_]AU|en[-_]IE/i]),
  }
}

export function useSpeech() {
  const [on, setOn] = useState(true)
  const [ready, setReady] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const voices = useRef<Record<Speaker, SpeechSynthesisVoice | null>>({
    shopper_agent: null, merchant_agent: null, human: null,
  })
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window

  useEffect(() => {
    if (!supported) return
    const load = () => {
      const all = window.speechSynthesis.getVoices()
      if (!all.length) return
      voices.current = assign(all)
      setReady(true)
    }
    load()
    window.speechSynthesis.addEventListener('voiceschanged', load)
    return () => window.speechSynthesis.removeEventListener('voiceschanged', load)
  }, [supported])

  const cancel = useCallback(() => {
    if (!supported) return
    window.speechSynthesis.cancel()
    setSpeaking(false)
  }, [supported])

  const speak = useCallback((text: string, who: Speaker) => {
    if (!supported || !on || !text.trim()) return
    const u = new SpeechSynthesisUtterance(
      // "₹2,990" reads as a glyph salad; say it the way a person would.
      text.replace(/₹\s?([\d,]+)/g, (_m, n) => `${String(n).replace(/,/g, '')} rupees`),
    )
    const v = voices.current[who]
    if (v) { u.voice = v; u.lang = v.lang }
    u.rate = who === 'human' ? 1.0 : 1.03
    u.pitch = who === 'merchant_agent' ? 0.95 : 1.0
    u.onstart = () => setSpeaking(true)
    u.onend = () => setSpeaking(window.speechSynthesis.pending)
    u.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(u)
  }, [supported, on])

  // Never leave a voice talking to an empty room.
  useEffect(() => () => { if (supported) window.speechSynthesis.cancel() }, [supported])
  useEffect(() => { if (!on) cancel() }, [on, cancel])

  return { supported, on, setOn, ready, speaking, speak, cancel,
           voices: voices.current }
}

/* ------------------------------------------------------------ recognition */

export function parseIntent(raw: string): Intent {
  const t = raw.toLowerCase().trim()
  if (!t) return { t: 'unknown', text: raw }

  if (/\b(stop|quiet|be quiet|shut up|halt|enough)\b/.test(t)) return { t: 'stop' }
  if (/\b(reset|start over|clear|from the top)\b/.test(t)) return { t: 'reset' }
  if (/\b(decline|deny|cancel it|reject|don'?t buy|do not buy)\b/.test(t))
    return { t: 'decline' }
  if (/\b(approve|approved|confirm|go ahead|do it|buy it|yes please|yep|yes)\b/.test(t))
    return { t: 'approve' }

  // Act selection by what the buyer actually says, not by act number.
  if (/pashmina|shawl|change of plan|instead/.test(t)) return { t: 'act', act: 'act3' }
  if (/jutti|kolhapuri|leather/.test(t)) return { t: 'act', act: 'act2' }
  if (/gift|polyester|friday|under (three|3)|3000|three thousand/.test(t))
    return { t: 'act', act: 'act1' }
  if (/\b(act|scene) ?(one|1)\b/.test(t)) return { t: 'act', act: 'act1' }
  if (/\b(act|scene) ?(two|2)\b/.test(t)) return { t: 'act', act: 'act2' }
  if (/\b(act|scene) ?(three|3)\b/.test(t)) return { t: 'act', act: 'act3' }

  if (/\b(run|go|start|begin|play)\b/.test(t)) return { t: 'run' }
  return { t: 'unknown', text: raw }
}

type Rec = {
  start(): void; stop(): void; abort(): void
  continuous: boolean; interimResults: boolean; lang: string
  onresult: ((e: any) => void) | null
  onerror: ((e: any) => void) | null
  onend: (() => void) | null
}

export function useListening(onIntent: (i: Intent, heard: string) => void) {
  const [listening, setListening] = useState(false)
  const [heard, setHeard] = useState('')
  const [error, setError] = useState<string | null>(null)
  const rec = useRef<Rec | null>(null)
  const cb = useRef(onIntent)
  cb.current = onIntent

  const Ctor = typeof window !== 'undefined'
    ? ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)
    : undefined
  const supported = !!Ctor

  const stop = useCallback(() => {
    rec.current?.stop()
    setListening(false)
  }, [])

  const start = useCallback(() => {
    if (!Ctor) return
    rec.current?.abort()
    const r: Rec = new Ctor()
    r.continuous = false
    r.interimResults = true
    r.lang = 'en-IN'
    r.onresult = (e: any) => {
      let interim = '', fin = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const txt = e.results[i][0].transcript
        if (e.results[i].isFinal) fin += txt; else interim += txt
      }
      setHeard(fin || interim)
      if (fin) {
        setListening(false)
        cb.current(parseIntent(fin), fin.trim())
      }
    }
    r.onerror = (e: any) => {
      setError(e?.error === 'network'
        ? 'Speech recognition needs network. Use the keys instead.'
        : e?.error === 'not-allowed'
        ? 'Microphone blocked. Allow it in the address bar.'
        : `Mic error: ${e?.error ?? 'unknown'}`)
      setListening(false)
    }
    r.onend = () => setListening(false)
    rec.current = r
    setHeard(''); setError(null); setListening(true)
    try { r.start() } catch { setListening(false) }
  }, [Ctor])

  useEffect(() => () => rec.current?.abort(), [])

  return { supported, listening, heard, error, start, stop,
           clear: () => { setHeard(''); setError(null) } }
}
