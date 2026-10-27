# Clap and trilingual voice acceptance — 2026-10-27

Status: local detector/intent candidate. **Real audio/clap and heard trilingual
provider playback BLOCKED** (no physical mic/speaker or configured provider used).

The SDK uses a local AudioWorklet with zero output and bounded10ms mono windows.
There is no continuous audio upload. At most one PCM window is unacknowledged;
a busy main thread causes input drops rather than an unbounded MessagePort queue.
Audio windows older than250ms or more than50ms in the future are dropped.
This can miss claps under UI load; it does not replay stale buffered sound. ClapDetector requires a sharp broadband rise,
minimum amplitude, noise-relative contrast and rapid decay; repeated events have
>=500ms configurable cooldown (default1200ms). Optional approaching-hand timing can
corroborate audio, but cannot create an event without acoustic evidence. Default
sensitivity1; allowed0.5..2. Suppress processing during EZO speech via the SDK's
setInteraction('speaking') to reduce feedback. It does not enable listening/STT.

This is a **heuristic transient detector**, not a validated clap classifier. Finger
snaps, tapping, impacts or short speech plosives can cause false positives; distant,
soft or reverberant claps may be missed. Threshold confidence is an evidence score,
not a calibrated probability. Hand timing can help but is not acoustic proof.
A clap can request only acknowledgement. It never authorizes destructive action,
message sending, filesystem access, tool execution or an independent microphone mode.

## Deterministic contract

- uz: `Eshitaman seni.`
- en: `I'm listening.`
- ru: `Я тебя слушаю.`

Language is supplied by actual conversation/user selection. No visual language
inference. All intents carry authorization:acknowledgement_only and
startListening:false. When permission is denied, the client must provide a clearly
manual Listen/acknowledgement action; no pretend hearing. The example's manual
control creates no fake ClapDetected. Provider-unavailable reports unavailable,
never claimed speech playback. No browser synthetic-voice downgrade is hidden.

VoiceReaction accepts an AcknowledgementPlayer bridge to existing authenticated
server TTS (voice routes in apps/api/src/ezo_api/api/routes/voice.py). Existing
ElevenLabs and OpenAI adapters remain untouched. No API credential belongs in this
SDK. Current backend configuration chooses provider voice globally; per-language
voice-ID routing is a **proposal**, not newly implemented server behavior here.
Claude should evaluate per-language naturally lower-register presets/IDs with
owner consent, calm delivery and intelligible Uzbek/English/Russian. Do not imitate
actors or force low pitch. Do not claim a provider supports a language until tested.

Player.play(intent, AbortSignal, emit) must synthesize only that authorized text
through existing authentication/budget/privacy policy, play actual decoded audio,
and resolve when playback completes. Abort must stop both pending work and playback.
Emit start only after audio starts, level only from actual decoded waveform RMS,
end on completion/stop, unavailable/error honestly. Stale callbacks after cancellation
are fenced. No viseme/phoneme events are invented. Map level to avatar.setLevel and
restore existing activity state on completion; `setInteraction('speaking')` suppresses
clap detection. See [the typed integration](HUMANOID_PERCEPTION_CONTRACT.md).

## Automated evidence

Synthetic PCM tests exercise a broadband pulse+decay, noise, sustained low-frequency
speech-like sine, sustained transients, cooldown, stale/invalid PCM, input bounds,
optional hand timing, denied/late microphone grants, graph cleanup, and abort.
Those signals are not a corpus of real speech/claps. Real AudioWorklet starts and
stops under Chromium fake-media. No physical acoustic accuracy metric is claimed.
All three exact acknowledgement strings and unavailable/cancellation playback
contracts are tested. An absent bridge is used in the local example, so it never
claims audible speech. No ElevenLabs/OpenAI/Claude live request was made.

## Remaining permissioned acceptance

1. On an authorized PC, explicitly enable **only** clap mic, confirm visible active
   indicator. With camera off, ordinary voice, music, typing, taps and ambient noise
   should not routinely trigger acknowledgements. Record false-positive counts over
   a timed session, not an invented percentage.
2. Clap singly and repeatedly at several distances, room noise/reverb levels and
   sensitivities. Record trial count/detections/false positives and cooldown timing.
   Enable optional visual corroboration and repeat with actual hand landmarks.
   No sound event may occur from silent hand movement alone.
3. Deny/revoke permission, hide app, unplug mic, stop during prompt/worklet loading.
   All tracks, graph, port and listeners must close. Returning does not auto-enable.
4. Claude connects actual provider bridge using server secrets/budget policy; owner
   authorizes any billable calls separately. Test UZ, EN and RU selected in UI.
   A human listener must confirm text heard, pronunciation, deep-natural timbre,
   calm pacing, no clipping, start/stop and non-metallic sound. Record provider/model/
   configured voice and subjective feedback, without exposing keys.
5. During speaking, suppress clap input. Interrupt playback and verify no stale jaw
   level, late sound or unexpected listening restart. When provider/key/quota is
   missing, show unavailable and manual controls. Measure real clap-to-audio-start
   p50/p95 latency only with working physical input/provider playback.

No audio files, recording, provider completion, premium quality or heard trilingual
speech is fabricated. These gates remain open pending approved physical/provider
access and shipping-client integration by Claude Max.
