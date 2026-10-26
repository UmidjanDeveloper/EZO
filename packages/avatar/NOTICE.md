# Notices — `@ezo/avatar`

The humanoid figure, its shaders, states and voice-level code are EZO's own work.

## Design pattern adapted from APEX-UI (MIT)

`src/frame.ts` (the voice frame: a thin ring, an equaliser and a state word around the
figure, with a dashed orbit that turns while the agent is busy) adapts the **interface
pattern** of the orb in [APEX-UI](https://github.com/RubenM1990/APEX-UI) by Ruben
Mouradian (Reznikov Engineering), released under the MIT License:

> Copyright (c) 2026 Ruben Mouradian (Reznikov Engineering)
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this
> software and associated documentation files (the "Software"), to deal in the Software
> without restriction, including without limitation the rights to use, copy, modify,
> merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
> permit persons to whom the Software is furnished to do so, subject to the following
> conditions: The above copyright notice and this permission notice shall be included in
> all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS",
> WITHOUT WARRANTY OF ANY KIND.

What was taken: the composition (ring → equaliser → state word → orbit), the idea of a
state-driven dashed orbit and of an equaliser that is calm on standby and alive when the
agent is active.

What was not taken: no APEX-UI source code, JSX, CSS, gold palette, the "Apex" name or
Reznikov Engineering branding (the README excludes the name and branding from the
licence), and nothing from the private Apex humanoid, which is not part of that
repository. EZO's frame is drawn from scratch in EZO's own cyan/gold palette, and its
equaliser follows a measured voice level instead of a timed animation.

APEX-UI itself credits two MIT components from 21st.dev (a shader background and an
overview lamp panel); neither is used by EZO.
