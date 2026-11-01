import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Audit, Checks, Gate, Lane, MandateCard, ReceiptCard, Verdict, useAutoScroll,
} from './components'
import { useRun } from './useRun'
import { useListening, useSpeech, type Intent } from './useVoice'

export default function App() {
  const [act, setAct] = useState('act1')
  const [mode, setMode] = useState<'replay' | 'live'>('replay')
  // Projector scaling. A laptop-tuned layout is unreadable from row 10.
  const [zoom, setZoom] = useState(1)
  useEffect(() => {
    document.documentElement.style.setProperty('--zoom', String(zoom))
  }, [zoom])
  const cycleZoom = useCallback(
    () => setZoom(z => (z >= 1.3 ? 1 : z === 1 ? 1.15 : 1.3)), [])

  const voice = useSpeech()
  const voiceOn = voice.supported && voice.on

  // Latest-value refs: the SSE tap is installed once but must see fresh state.
  const speakRef = useRef(voice.speak)
  speakRef.current = voice.speak

  /** Speak turns as they open, so audio and captions start together. */
  const onEvent = useCallback((e: any) => {
    if (!e?.speak) return
    if (e.kind === 'agent_message_start') speakRef.current(e.text, e.agent)
    else if (e.kind === 'user_message') speakRef.current(e.text, 'human')
  }, [])

  const { state, acts, liveAvailable, run, stop, reset, approve } =
    useRun('demo', onEvent)

  const busy = state.status === 'running' || state.status === 'awaiting_human'

  const start = useCallback((which = act) => {
    if (busy) return
    voice.cancel()
    run(which, mode, voiceOn)
  }, [busy, run, act, mode, voiceOn, voice])

  const stopAll = useCallback(() => { voice.cancel(); stop() }, [voice, stop])
  const resetAll = useCallback(() => { voice.cancel(); reset() }, [voice, reset])

  /** A spoken command becomes the same action a key would trigger. */
  const onIntent = useCallback((i: Intent) => {
    switch (i.t) {
      case 'act':
        setAct(i.act)
        if (!busy) start(i.act)
        break
      case 'run':     start(); break
      case 'approve': if (state.approval) approve(true); else start(); break
      case 'decline': if (state.approval) approve(false); break
      case 'reset':   resetAll(); break
      case 'stop':    stopAll(); break
    }
  }, [busy, start, approve, state.approval, resetAll, stopAll])

  const mic = useListening(onIntent)

  // Re-pin on new items AND on streamed tokens, so long turns stay in view.
  const leftRef = useAutoScroll(
    state.left.length + (state.left.at(-1)?.k === 'agent'
      ? (state.left.at(-1) as { text: string }).text.length : 0))
  const rightRef = useAutoScroll(
    state.right.length + (state.right.at(-1)?.k === 'agent'
      ? (state.right.at(-1) as { text: string }).text.length : 0))
  // The gate, the receipt and a refusal each pin themselves into view, so
  // the centre pane stops chasing the bottom whenever one of them is up.
  const awaiting = state.status === 'awaiting_human' && !state.approvalResolved
  const pinned = awaiting || !!state.receipt || !!state.blocked
  const midRef = useAutoScroll(
    state.decisions.length + (state.receipt ? 1 : 0) + (state.approval ? 1 : 0),
    !pinned)

  // Presenter mode: 1/2/3 pick an act, Enter runs, A approves, M talks.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t && /^(INPUT|TEXTAREA)$/.test(t.tagName)) return
      const k = e.key.toLowerCase()
      if (e.key >= '1' && e.key <= String(Math.min(9, acts.length))) {
        const picked = acts[Number(e.key) - 1]
        if (picked && !busy) setAct(picked.id)
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault(); start()
      } else if (k === 'm') {
        mic.listening ? mic.stop() : mic.start()
      } else if (k === 'v') {
        voice.setOn(v => !v)
      } else if (k === 'z') {
        cycleZoom()
      } else if (k === 'r') {
        resetAll()
      } else if (e.key === 'Escape') {
        stopAll()
      } else if (k === 'a' && state.approval) {
        approve(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [acts, busy, start, resetAll, stopAll, approve, state.approval, mic, voice,
      cycleZoom])

  const current = acts.find(a => a.id === act)
  const lastDecision = state.decisions.at(-1)

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="dots"><i /><i /><i /><i /></div>
          <div>
            <h1>Agentic Commerce</h1>
            <div className="sub">Mandate-bound checkout</div>
          </div>
        </div>

        <div className="acts" role="group" aria-label="Demo acts">
          {acts.map((a, i) => (
            <button key={a.id} className="act" disabled={busy}
                    aria-pressed={act === a.id}
                    onClick={() => setAct(a.id)} title={a.beat}>
              <kbd>{i + 1}</kbd><span className="lbl">{a.title}</span>
            </button>
          ))}
        </div>

        <div className="spacer" />

        {voice.supported && (
          <button
            className={`mode ${voice.on ? 'voice' : 'off'}`}
            aria-pressed={voice.on}
            title="Agents speak their turns aloud (V)"
            onClick={() => voice.setOn(v => !v)}>
            <span className={`pip${voice.speaking ? ' pulse' : ''}`} />
            <span className="lbl">{voice.on ? 'Voice on' : 'Voice off'}</span>
          </button>
        )}

        <button
          className={`mode ${mode === 'live' ? 'live' : liveAvailable ? '' : 'off'}`}
          disabled={busy}
          title={liveAvailable
            ? 'Toggle between the real ADK runner and deterministic replay'
            : 'Live mode needs GOOGLE_API_KEY. Replay runs the real mandate either way.'}
          onClick={() => liveAvailable &&
            setMode(m => (m === 'live' ? 'replay' : 'live'))}>
          <span className="pip" />
          <span className="lbl">
            {mode === 'live' ? 'Live · Gemini via ADK' : 'Replay · offline'}
          </span>
        </button>

        {mic.supported && (
          <button className={`mic${mic.listening ? ' hot' : ''}`}
                  onClick={() => mic.listening ? mic.stop() : mic.start()}
                  title="Hold a conversation with the agent (M)">
            <span className="ico" aria-hidden>●</span>
            <span className="lbl">{mic.listening ? 'Listening…' : 'Speak'}</span>
          </button>
        )}

        <button className="mode" onClick={cycleZoom}
                title="Scale the whole UI for a projector (Z)">
          <span className="pip" style={{ background: '#BDC1C6', boxShadow: 'none' }} />
          <span className="zl">{Math.round(zoom * 100)}%</span>
        </button>

        {busy
          ? <button className="btn btn-ghost" onClick={stopAll}>Stop</button>
          : <button className="btn btn-ghost" onClick={resetAll}>Reset</button>}
        <button className="btn btn-primary" onClick={() => start()} disabled={busy}>
          Run act
        </button>
      </header>

      {(mic.heard || mic.error) && (
        <div className={`heard${mic.error ? ' bad' : ''}`}>
          <span className="lb">{mic.error ? 'Mic' : 'Heard'}</span>
          <span className="tx">{mic.error ?? mic.heard}</span>
          <button className="x" onClick={mic.clear} aria-label="Dismiss">×</button>
        </div>
      )}

      <div className="panes">
        {/* ---------------- buyer + shopper agent ---------------- */}
        <section className="pane">
          <div className="pane-head">
            <div>
              <div className="t">Buyer &amp; shopper agent</div>
              <div className="d">Acts for Priya, bound by the mandate</div>
            </div>
          </div>
          <div className="pane-body" ref={leftRef}>
            {state.error && <div className="err">{state.error}</div>}
            {state.left.length === 0
              ? <div className="empty">
                  {mic.supported
                    ? <>Press <span className="k">M</span> and say
                        <br /><em>"I need a gift under three thousand rupees"</em></>
                    : <>Pick an act and press <span className="k">Enter</span>.</>}
                  <br /><br />
                  <span className="k">1</span> <span className="k">2</span>{' '}
                  <span className="k">3</span> acts ·{' '}
                  <span className="k">A</span> approve ·{' '}
                  <span className="k">V</span> voice ·{' '}
                  <span className="k">Z</span> zoom ·{' '}
                  <span className="k">R</span> reset
                </div>
              : <Lane items={state.left} />}
          </div>
        </section>

        {/* ---------------- mandate ---------------- */}
        <section className="pane center">
          <div className="pane-head">
            <div>
              <div className="t">Mandate &amp; trust layer</div>
              <div className="d">Enforced in Python, not in a prompt</div>
            </div>
          </div>
          <div className="pane-body" ref={midRef}>
            {state.mandate
              ? <MandateCard m={state.mandate} />
              : <div className="empty">
                  No mandate issued yet.<br />
                  This pane is the only thing that can say no.
                </div>}

            {state.approval && !state.approvalResolved && (
              <Gate a={state.approval}
                    hint={mic.supported ? 'or just say "approve"' : undefined}
                    onApprove={() => approve(true)}
                    onDeny={() => approve(false)} />
            )}

            {state.receipt && <ReceiptCard r={state.receipt} />}
            {state.blocked && <Verdict d={state.blocked} pin />}
            {/* While the gate is up it already states the amount and the
                reason, so the matching verdict card would just be a second
                yellow block saying the same thing. */}
            {lastDecision && !state.receipt && !state.blocked && !awaiting && (
              <Verdict d={lastDecision} />
            )}
            {lastDecision && <Checks d={lastDecision} />}
            {state.mandate && <Audit entries={state.mandate.audit} />}
          </div>
        </section>

        {/* ---------------- merchant agent ---------------- */}
        <section className="pane">
          <div className="pane-head">
            <div>
              <div className="t">Merchant agent &amp; A2A</div>
              <div className="d">Separate principal, separate interests</div>
            </div>
          </div>
          <div className="pane-body" ref={rightRef}>
            {state.right.length === 0
              ? <div className="empty">
                  The store's agent and the agent-to-agent<br />
                  protocol traffic show up here.
                </div>
              : <Lane items={state.right} />}
          </div>
        </section>
      </div>

      <footer className="statusbar">
        <span>
          {state.status === 'idle' && 'Ready'}
          {state.status === 'running' && <><b>Running</b> · {state.title}</>}
          {state.status === 'awaiting_human' && <><b>Paused</b> · waiting on a human</>}
          {state.status === 'done' && (
            <b>{state.finish === 'blocked_by_mandate' ? 'Blocked by mandate'
              : state.finish === 'declined_by_human' ? 'Declined by human'
              : 'Complete'}</b>
          )}
        </span>
        <span className="beat">{state.beat ?? current?.beat}</span>
        <span className="sp" />
        {voiceOn && voice.voices.shopper_agent && (
          <span title="On-device voices, no network">
            {voice.voices.shopper_agent.name} / {voice.voices.merchant_agent?.name}
          </span>
        )}
        <span>Google ADK · {state.mode === 'live' ? 'gemini-2.0-flash' : 'deterministic replay'}</span>
        <span>Pune Product × GCC Forum</span>
      </footer>
    </div>
  )
}
