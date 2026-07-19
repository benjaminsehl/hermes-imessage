# hermes-imessage

Current, tested BlueBubbles/iMessage UX patches for [Hermes Agent](https://github.com/NousResearch/hermes-agent).

Hermes now includes much of the original project upstream: paragraph-aware iMessage bubbles, pagination-suffix removal, platform-specific response guidance, configurable progress display, and BlueBubbles webhook management. This repository now focuses only on behavior that is still missing from current Hermes.

## Current additions

### Contextual quick acknowledgment

For substantive iMessages, Hermes calls a fast auxiliary model and sends a short acknowledgment before the main agent starts. The acknowledgment context is passed directly into that exact main-agent invocation through Hermes' API-content sidecar; prior history is not mutated, no synthetic user role is added, and a failed or cancelled turn cannot leak the note into a later request.

The acknowledgment is skipped for slash commands and trivial messages such as greetings, `ping`, thanks, and yes/no replies. One monotonic deadline covers both generation and BlueBubbles delivery, with a bounded slice reserved for fallback delivery and without waiting for slow cancellation cleanup. Instructions use a system message, and both generated text and configured fallback text must match a strict pending-work grammar; otherwise Hermes uses its safe built-in fallback. A BlueBubbles send failure never aborts the main turn.

### Duplicate-delivery protection

BlueBubbles can emit one iMessage as both `new-message` and `updated-message`, sometimes with different chat identifier fields. Hermes previously treated both as separate requests and sent two full replies.

The current patch protects both relevant layers:

- Webhook registration is canonicalized to IPv4 `127.0.0.1`; equivalent `localhost` registrations, duplicate callbacks, and stale event subscriptions are removed before one healthy callback is registered.
- Validated inbound messages reserve their stable BlueBubbles GUID before attachment downloads, using a bounded 2,048-entry, 15-minute metadata-only completed-message cache and a 64-attachment per-message limit even when BlueBubbles omits the message GUID. Equivalent in-flight deliveries join one setup outcome, share one ordered download/dispatch sequence, and a waiting duplicate takes over if the owner fails.
- Outcome joining is capped at 64 waiters, a 30-second request-wide deadline, and four joined outcomes. Additional, timed-out, or repeatedly displaced requests receive retryable HTTP 503 instead of retaining unbounded HTTP connections.
- In-flight reservations are never TTL/LRU-evicted. Capacity consisting entirely of in-flight work returns retryable HTTP 503 rather than creating duplicate work.
- New attachments are serialized against any in-flight owner. A genuinely new attachment arriving after the original event was consumed is dispatched once as an attachment-only enrichment. Failed or cancelled enrichment rolls back to the prior completed reservation so BlueBubbles can retry it.

Different GUIDs still dispatch normally, malformed payloads cannot poison a later valid retry, and Apple CAF voice-note classification is preserved.

## Compatibility

The current patch is generated and tested against Hermes Agent commit:

```text
dd418284d bench(desktop): trustworthy --spawn stream numbers + real baseline (#67694)
```

Always run `git apply --check` before applying it to a newer Hermes checkout.

## Durable update channel

The preferred installation is the maintained `benjaminsehl/hermes-agent` fork. Its `main` branch contains current Nous Research `main` plus this implementation. A scheduled fail-closed workflow merges upstream into a candidate, runs the 192-test BlueBubbles contract gate, and advances fork `main` only when every check passes. Conflicts or regressions leave the last known-good release untouched.

The live Hermes checkout should use the fork as `origin`, Nous Research as `upstream`, and track `origin/main`. Plain `hermes update` then consumes only tested downstream releases; it does not depend on restoring an uncommitted patch from git stash.

Fork operations and recovery are documented in `DOWNSTREAM_BLUEBUBBLES.md` in the maintained fork.

The local drift watchdog is versioned at `scripts/hermes_update_drift_audit.py`; `~/.hermes/scripts/hermes_update_drift_audit.py` symlinks to it for the scheduled audit. It separately reports live-vs-tested-release drift and tested-fork-vs-Nous drift, so intentional downstream commits are not mistaken for update risk.

## Manual patch installation

Use this recovery path for an upstream checkout that is not following the maintained fork:

```bash
cd ~/.hermes/hermes-agent

git apply --check /path/to/hermes-imessage/patches/current-bluebubbles-ack-dedupe.patch
git apply /path/to/hermes-imessage/patches/current-bluebubbles-ack-dedupe.patch
```

Enable the acknowledgment in `~/.hermes/config.yaml`:

```yaml
display:
  platforms:
    bluebubbles:
      quick_ack_enabled: true
      quick_ack_model: gpt-5.4-mini
      quick_ack_fallback: "Got it — I’m looking into that."
      quick_ack_timeout_seconds: 3
```

`quick_ack_model` is optional. When omitted, Hermes uses its normal auxiliary-model routing. The timeout is clamped to 0.5–10 seconds.

BlueBubbles `ReadTimeout` failures with an empty exception message retain their exception class. Because the server may already have delivered the bubble before its REST response times out, Hermes does not misclassify that ambiguous outcome as a formatting error and send an extra fallback bubble.

Restart the gateway after applying:

```bash
hermes gateway restart
```

## Verification

From the Hermes checkout:

```bash
python -m pytest \
  tests/gateway/test_bluebubbles.py \
  tests/gateway/test_prompt_tail_freeze.py \
  tests/gateway/test_run_progress_topics.py \
  tests/gateway/test_aiohttp_body_caps.py \
  -o addopts=
```

Then send one substantive iMessage. Expected behavior:

1. One short contextual acknowledgment arrives first.
2. One main response arrives afterward.
3. An equivalent later `updated-message` for the same GUID does not start a second agent run; an update containing genuinely new media produces one attachment-only enrichment.
4. `ping`, `thanks`, and slash commands do not receive a separate acknowledgment.
5. BlueBubbles lists exactly one equivalent Hermes webhook callback.

## Repository layout

```text
patches/
  current-bluebubbles-ack-dedupe.patch  # Current tested patch
  legacy/                               # Historical patches; do not apply to current Hermes
scripts/
  hermes_update_drift_audit.py          # Fork-aware local update watchdog
skill/
  imessage-ux/
    SKILL.md
```

The files under `patches/legacy/` are preserved only as historical reference. They target an older Hermes architecture and do not apply cleanly to current main.

## License

MIT
