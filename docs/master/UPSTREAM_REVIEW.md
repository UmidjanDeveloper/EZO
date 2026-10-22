# Pinned upstream review — 22 October 2026

Historical six-repository selection snapshot. The owner subsequently made all eight
upstreams mandatory, including Microsoft JARVIS and OpenJarvis. Current implemented
features and exclusions are tracked in [UPSTREAM_IMPLEMENTATION_MATRIX.md](UPSTREAM_IMPLEMENTATION_MATRIX.md).
The earlier no-integration decisions below are not a waiver of that expanded mission.

Upstream repositories were fetched read-only, with no install scripts, agents,
models or upstream binaries executed. This is a component-selection review, not a
complete audit of six projects. Issue reports are untrusted allegations unless
corroborated; empty advisory pages never establish absence of vulnerabilities.
Raw source snapshots, public security pages and issue captures are retained in
`/workspace/ezo-master-evidence`; no private source was uploaded upstream.

| Upstream / exact inspected commit | License / version | Decision and source boundary |
|---|---|---|
| [LlamaIndex](https://github.com/run-llama/llama_index/tree/619d74664e8404612038bc15a1a40c686037277c) | MIT; core 0.14.25 | Pin `llama-index-core==0.14.25`; use `core/schema.py` TextNode for outbound, validated EZO context interchange. EZO retains retrieval ACLs, pgvector, source identity, budgets and provider routing. No meta-package, upstream agents, Python/SQL query engines, file readers, pickle deserialization or downloaded skills. |
| [Ruflo](https://github.com/ruvnet/ruflo/tree/5d99b57e7862c0623cf26e0c152dff60e3b50346) | MIT; root claude-flow 3.59.14 | Read CLI entrypoint, security exports, security policy and manifest. Keep existing disabled coordination boundary. Shell-capable CLI/MCP is unsuitable for direct user/model access; no automatic install, swarm launch or inherited secrets. |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio/tree/28bf2c7a83b8a64836297340c52a45d716684aed) | AGPL-3.0-only; 0.5.7 | Reviewed LICENSE, LICENSE-NOTICE, backend path-security and API dependency source. **No code copied.** Existing separate HTTP adapter remains optional; app license and model-weight rights are distinct. Default OmniVoice weights' CC-BY-NC and tokenizer/community terms are not cleared by app licensing. Any future copying requires explicit compatible licensing decision and source-offer review. |
| [APEX-UI](https://github.com/RubenM1990/APEX-UI/tree/a8732fad1078a809cadfa810cb0d89cf4445dbed) | MIT; 1.0.0 | Read Next page/layout, weather API route and manifest. Design reference only; no frontend copied or changed without Antigravity coordination. Weather route introduces external geolocation handling that EZO does not need. |
| [REA](https://github.com/morluto/rea/tree/c8ed32853881b08aa83459d4da55a28a4e09b0c8) | MIT root; 6.7.0; bundled tools have separate notices | Read CLI composition, capability requirements, security policy and bundled license inventory. No integration: broad capture/debugger/native capabilities are outside Student's reading boundary. Future authorized reverse engineering requires a separate owner-scoped task and isolated tool policy. |
| [Supabase](https://github.com/supabase/supabase/tree/1055bc6b458d58a7532f03ad2e9ed34983077d40) | Apache-2.0 root; monorepo 0.0.0 is not a hosted service version | Reuse existing private REST Storage and PostgreSQL adapters. Read Storage access-control/download and RLS docs plus compose source. Do not self-host the whole Supabase stack or expose Studio/MCP. Service-role keys bypass RLS: authorization remains server-side; browser never receives them. |

The LlamaIndex MIT notice is retained in
[LLAMAINDEX_LICENSE.txt](../third-party/LLAMAINDEX_LICENSE.txt). Other upstream code
was not vendored. Transitive package licenses remain attached to installed wheels;
a distribution-wide license inventory remains a release review gate. Do not infer
that every dependency shares the root repository license.

## Security findings actually inspected

- Ruflo [GHSA-c4hm-4h84-2cf3](https://github.com/ruvnet/ruflo/security/advisories/GHSA-c4hm-4h84-2cf3),
  **CVE-2026-59726**, critical: unauthenticated MCP bridge shell execution, provider
  secret exposure and persisted AgentDB poisoning; advisory affected npm ruflo
  `<3.16.3`, fixed `3.16.3`. A root `claude-flow` version is not proof that any
  separately deployed `ruflo` bridge is patched. EZO does not deploy that bridge.
- LlamaIndex [#22232](https://github.com/run-llama/llama_index/issues/22232)
  reports `llama-index-experimental` PandasQueryEngine safe_eval escape;
  [#22317](https://github.com/run-llama/llama_index/issues/22317) reports SharePoint
  file-name traversal. Neither component is installed or callable here. These
  reports are not treated as independently reproduced vulnerabilities in EZO.
- LlamaIndex [#22839](https://github.com/run-llama/llama_index/issues/22839) discusses
  NLTK security-version compatibility; this lock resolves NLTK **3.10.4**. No NLTK
  downloader or untrusted model/pickle load is invoked by our adapter.
- Supabase [#51877](https://github.com/supabase/supabase/issues/51877) reports
  unauthenticated self-hosted Studio MCP SQL/migration execution. This allegation
  does not establish exposure of the hosted Storage service. No Studio/MCP is
  installed, deployed or exposed by EZO.
- REA [#6212](https://github.com/morluto/rea/issues/6212) concerns Ghidra JVM argument
  environment overrides. No REA/Ghidra runtime is enabled.

## Dependency cost

Core adds 35 locked distributions to the existing runtime (36 installs including
the rebuilt EZO editable package). This is a real attack-surface and image-cost
increase, accepted here for the explicitly requested LlamaIndex interchange;
full framework orchestration is deliberately excluded. It is not a zero-cost
serialization helper. Local import took about 1.66 seconds on this development
host, **not** a 4/8 GB VM benchmark. Current audits and image scans, including
remaining distro vulnerabilities, are recorded separately in VALIDATION.md.
