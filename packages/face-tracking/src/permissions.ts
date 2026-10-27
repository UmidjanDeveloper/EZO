/** Query does not request permission. Unsupported platforms fall back to track ended/mute. */
export function watchRevocation(kind: 'camera' | 'microphone', signal: AbortSignal, onDenied: () => void): void {
    if (!navigator.permissions?.query)
        return;
    void navigator.permissions.query({ name: kind as PermissionName }).then(status => {
        if (signal.aborted)
            return;
        const changed = () => { if (status.state === 'denied' && !signal.aborted)
            onDenied(); };
        status.addEventListener('change', changed);
        signal.addEventListener('abort', () => status.removeEventListener('change', changed), { once: true });
        changed();
    }).catch(() => { });
}
