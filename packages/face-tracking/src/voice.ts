import type { ClapDetected, Language, PlaybackEvent } from './types';
export const ACKNOWLEDGEMENTS: Readonly<Record<Language, string>> = Object.freeze({ uz: 'Eshitaman seni.', en: "I'm listening.", ru: 'Я тебя слушаю.' });
export interface AcknowledgementIntent {
    type: 'speak_acknowledgement';
    text: string;
    language: Language;
    style: 'calm-natural-deep';
    authorization: 'acknowledgement_only'; /** A clap does NOT grant listening consent. */
    startListening: false;
}
export function acknowledgement(event: ClapDetected, language: Language): AcknowledgementIntent {
    if (event.type !== 'clap_detected' || event.confidence < 0.7 || event.confidence > 1 || !Number.isFinite(event.confidence) || !Number.isFinite(event.timestampMs) || !Object.hasOwn(ACKNOWLEDGEMENTS, language))
        throw new Error('Invalid acknowledgement event/language');
    return { type: 'speak_acknowledgement', text: ACKNOWLEDGEMENTS[language], language, style: 'calm-natural-deep', authorization: 'acknowledgement_only', startListening: false };
}
/** Client supplies existing authenticated TTS + REAL playback; no browser/AI imitation fallback. */
export interface AcknowledgementPlayer {
    play(intent: AcknowledgementIntent, signal: AbortSignal, onPlayback: (event: PlaybackEvent) => void): Promise<void>;
}
export class VoiceReaction {
    private abort: AbortController | null = null;
    constructor(private readonly player: AcknowledgementPlayer | null, private readonly onPlayback: (event: PlaybackEvent) => void) { }
    async react(intent: AcknowledgementIntent): Promise<void> {
        this.stop();
        const abort = new AbortController();
        this.abort = abort;
        if (!this.player) {
            this.abort = null;
            this.onPlayback({ type: 'unavailable', timestampMs: performance.now() });
            return;
        }
        let began = false, ended = false;
        try {
            await this.player.play(intent, abort.signal, event => {
                if (abort.signal.aborted || this.abort !== abort || ended || !Number.isFinite(event.timestampMs))
                    return;
                if (event.type === 'start') {
                    if (began)
                        return;
                    began = true;
                }
                else if (event.type === 'level') {
                    if (!began || ended || !Number.isFinite(event.level))
                        return;
                    event = { ...event, level: Math.max(0, Math.min(1, event.level)) };
                }
                else
                    ended = true;
                this.onPlayback(event);
            });
        }
        catch {
            if (!abort.signal.aborted)
                this.onPlayback({ type: 'error', timestampMs: performance.now() });
        }
        finally {
            if (this.abort === abort) {
                this.abort = null;
                if (began && !ended)
                    this.onPlayback({ type: 'end', timestampMs: performance.now() });
            }
        }
    }
    stop() { if (this.abort) {
        this.abort.abort();
        this.abort = null;
        this.onPlayback({ type: 'end', timestampMs: performance.now() });
    } }
}
