/** Stable, non-biometric head attention. No identity, emotion or eye-gaze claims. */
export interface Attention { yaw: number; pitch: number }
const clamp = (v: number) => Math.max(-1, Math.min(1, Number.isFinite(v) ? v : 0));
export class AttentionFilter {
  private value: Attention = { yaw: 0, pitch: 0 };
  private last = -Infinity;
  private detectedAt = -Infinity;
  private calibration: Attention | null = null;
  /** Normalized head pose; monotonically increasing timestamps in seconds. */
  update(input: Attention | null, now: number): Attention | null {
    const dt = Math.max(0, Math.min(0.2, now - this.last));
    this.last = now;
    if (input && Number.isFinite(input.yaw) && Number.isFinite(input.pitch)) {
      if (!this.calibration) this.calibration = { ...input };
      let yaw = clamp((input.yaw - this.calibration.yaw) * 1.4);
      let pitch = clamp((input.pitch - this.calibration.pitch) * 1.4);
      if (Math.abs(yaw) < 0.045) yaw = 0;
      if (Math.abs(pitch) < 0.045) pitch = 0;
      // Reject a detection jump rather than whipping the figure around.
      if (Math.hypot(yaw - this.value.yaw, pitch - this.value.pitch) <= 0.85) {
        const k = 1 - Math.exp(-dt * 6);
        this.value = { yaw: this.value.yaw + (yaw - this.value.yaw) * k, pitch: this.value.pitch + (pitch - this.value.pitch) * k };
        this.detectedAt = now;
      }
    }
    return now - this.detectedAt <= 0.5 ? { ...this.value } : null;
  }
  reset() { this.calibration = null; this.value = { yaw: 0, pitch: 0 }; this.detectedAt = -Infinity; this.last = -Infinity; }
}
