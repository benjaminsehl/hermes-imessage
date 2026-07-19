---
name: imessage-ux
description: Optimizes Hermes responses over BlueBubbles with concise iMessage delivery, contextual pre-response acknowledgments, and duplicate-delivery protection
version: 2.3.0
author: Benjamin Sehl
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [iMessage, BlueBubbles, messaging, UX]
    requires_toolsets: []
    related_skills: [bluebubbles-channel-integration]
---

# iMessage UX optimization

Use this guidance when Hermes is responding through BlueBubbles/iMessage.

## Response style

- Write like a useful text conversation, not a report.
- Lead with the answer or result.
- Keep each thought short and conversational.
- Separate distinct thoughts with blank lines so paragraph-aware delivery can produce natural bubbles.
- Avoid headings and long lists unless the user asked for detail.
- Do not repeat a visible quick acknowledgment in the final response.
- Do not narrate internal agent mechanics or tool activity.

## Current adapter behavior

The current patch adds two behaviors that are not yet present on the tested Hermes main revision:

1. Contextual quick acknowledgment
   - BlueBubbles-only and disabled by default.
   - Uses Hermes' asynchronous auxiliary LLM router.
   - Skips slash commands, greetings, pings, thanks, and yes/no replies.
   - Uses one hard deadline across generation and BlueBubbles delivery, reserving a bounded slice for fallback sending without waiting for cancellation cleanup.
   - Places generation rules in a system message and accepts generated/configured text only when it matches a strict pending-work grammar; otherwise it uses the safe built-in fallback.
   - Passes the visible acknowledgment directly into the exact current main turn through the API-content sidecar without mutating prior history, adding a synthetic user role, or leaving reusable session-key state behind.
   - Preserves the exception class for empty-message BlueBubbles timeouts so an ambiguous, already-delivered send does not trigger an extra formatting fallback bubble.

2. Stable-GUID deduplication
   - Canonicalizes local webhook registration to IPv4 `127.0.0.1`.
   - Collapses equivalent `localhost`/`127.0.0.1` duplicate registrations and repairs stale event subscriptions.
   - Enforces the 64-attachment bound even when BlueBubbles omits the message GUID.
   - Reserves a validated iMessage GUID before attachment network/disk work, so equivalent `updated-message`/`new-message` deliveries join one outcome, share one download and one dispatch, and a waiting duplicate can take over after owner failure.
   - Caps outcome joining at 64 waiters, a 30-second request-wide deadline, and four joined outcomes; overflow, timeout, or repeated displacement returns retryable HTTP 503.
   - Keeps in-flight reservations out of TTL/LRU eviction; all-in-flight capacity pressure returns retryable HTTP 503.
   - Bounds metadata-only completed state to 2,048 entries for 15 minutes and each message to 64 attachment GUIDs; it does not retain raw webhook events and preserves BlueBubbles attachment order.
   - Serializes new media against an in-flight owner, then dispatches genuinely late media once as an attachment-only enrichment; failed or cancelled enrichment rolls back so BlueBubbles retries remain possible.

Hermes upstream already supplies paragraph-aware BlueBubbles delivery, pagination-suffix removal, platform response guidance, configurable progress display, and webhook registration management. Do not reapply the historical implementations of those features.

## Configuration

```yaml
display:
  platforms:
    bluebubbles:
      quick_ack_enabled: true
      quick_ack_model: gpt-5.4-mini
      quick_ack_fallback: "Got it — I’m looking into that."
      quick_ack_timeout_seconds: 3
```

The model is optional. The timeout is clamped to 0.5–10 seconds.

## Durable updates

Prefer the maintained `benjaminsehl/hermes-agent` fork as the live checkout's `origin`, with Nous Research configured as `upstream`. Fork `main` advances only after its scheduled upstream merge passes the BlueBubbles contract gate. This avoids Hermes' unsafe conflict path where a failed autostash restore resets to clean upstream and still restarts the gateway.

Keep this repository's current patch as portable recovery material, not as the primary live update mechanism. If upstream integration fails, leave fork `main` and the live gateway on the last known-good commit, port the implementation in a candidate worktree, rerun the full contract and review gates, and only then advance the fork.

## Manual patch recovery

```bash
cd ~/.hermes/hermes-agent
git apply --check /path/to/hermes-imessage/patches/current-bluebubbles-ack-dedupe.patch
git apply /path/to/hermes-imessage/patches/current-bluebubbles-ack-dedupe.patch
hermes gateway restart
```

Do not apply files under `patches/legacy/` to current Hermes.

## Verification

1. Run the focused gateway tests documented in the repository README.
2. Send a substantive iMessage and confirm one acknowledgment arrives before one final reply.
3. Send `ping`; confirm there is no separate acknowledgment.
4. Confirm gateway logs show only one inbound agent run for a BlueBubbles GUID even if both `new-message` and `updated-message` are emitted.

## Pitfalls

- Two full replies can come from duplicate registrations or from two event types carrying the same GUID. Verify both the webhook registry and gateway inbound logs.
- A fast model must be available through Hermes' auxiliary routing. Generation failure should produce the configured fallback, not block the main turn.
- Keep acknowledgments noncommittal. They may say that Hermes is looking or checking, but must never claim the requested work is complete.
- Preserve prompt-cache and role-alternation invariants. Do not append acknowledgment text as an extra historical assistant turn or inject a synthetic user continuation.
