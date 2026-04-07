---
name: imessage-ux
description: Optimizes Hermes responses for iMessage via BlueBubbles -- shorter messages, multi-bubble delivery, contextual acknowledgments, and input debouncing
version: 1.0.0
author: Benjamin Sehl
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [iMessage, BlueBubbles, messaging, UX]
    requires_toolsets: []
    related_skills: [bluebubbles-channels]
---

# iMessage UX Optimization

Makes Hermes feel native on iMessage by adapting its output style and delivery mechanics to how people actually text.

## When to Use

This skill is loaded automatically when the agent is responding via the BlueBubbles (iMessage) platform. It provides guidance on response formatting that works with the adapter-level patches.

## The Problem

By default, Hermes treats iMessage like Slack or Discord:
- Sends one giant message that gets split at arbitrary character limits
- Shows `(1/3)` pagination suffixes
- Spams tool-use progress as separate message bubbles (`browser_navigate: "..."`)
- No feedback while thinking (30+ seconds of silence)
- Responses are too long and formal for a texting context

## How It Works

This skill has two layers:

### 1. Adapter patches (applied to Hermes core)

These modify the BlueBubbles adapter and gateway to:

- **Split on paragraphs** -- each double-newline-separated block becomes its own iMessage bubble, so the model controls message boundaries by how it structures its output
- **Reduce chunk size** -- 800 chars max per bubble (down from 4,000), so overflow splits are still text-sized
- **Strip pagination** -- no `(1/3)` suffixes, bubbles flow naturally
- **Debounce input** -- 2-second buffer merges rapid messages (link previews, multi-bubble pastes) into one agent invocation
- **Suppress tool progress** -- platforms without message editing skip progress bubbles entirely
- **Contextual acknowledgment** -- a fast LLM call generates a brief, context-aware reply (e.g., "Let me check that out") before the main model starts, so the user isn't waiting in silence

### 2. System prompt injection (via session.py patch)

When the source platform is BlueBubbles, the session context includes:

> You are responding via iMessage. Keep responses short and conversational -- think texts, not essays. Structure longer replies as separate short thoughts, each separated by a blank line (double newline). Each block between blank lines will be delivered as its own iMessage bubble, so write accordingly: one idea per bubble, 1-3 sentences each. If the user needs a detailed answer, give the short version first and offer to elaborate.

This tells the model *why* paragraph breaks matter (they become separate bubbles) and sets the right tone.

## Installation

```bash
# Apply the three patches to your Hermes install
cd ~/.hermes/hermes-agent
git apply /path/to/patches/bluebubbles-ux.patch
git apply /path/to/patches/gateway-ack-and-progress.patch
git apply /path/to/patches/session-platform-notes.patch

# Install this skill
cp -r /path/to/skill/imessage-ux ~/.hermes/skills/imessage-ux

# Restart
hermes gateway restart
```

## Configuration

| Setting | Location | Default | Description |
|---------|----------|---------|-------------|
| Chunk size | `bluebubbles.py` `MAX_TEXT_LENGTH` | 800 | Max characters per bubble |
| Debounce window | `bluebubbles.py` `_DEBOUNCE_SECS` | 2.0 | Seconds to wait for more messages |
| Ack model | `run.py` ack block | `gpt-5.4-mini` | Fast model for acknowledgments |
| Ack max tokens | `run.py` ack block | 30 | Keep acks very short |

## Pitfalls

- **Ack model not configured**: If your LLM provider doesn't have the configured model, the ack falls back to "One sec..." silently. Check `hermes gateway status` and logs at `~/.hermes/logs/gateway.log`.
- **Debounce too aggressive**: If 2 seconds feels too slow, lower `_DEBOUNCE_SECS`. If you send long multi-part messages, you may need to raise it.
- **Code blocks**: The paragraph splitter won't break inside code fences -- those get handled by the base `truncate_message` which preserves code block boundaries.

## Verification

1. Send a message to Hermes via iMessage
2. You should see a brief contextual ack within ~1 second
3. The response should arrive as multiple short bubbles, not one wall of text
4. Send a message with a URL -- the debouncer should merge it with the link preview into one request
5. Ask something that triggers tool use -- you should NOT see `browser_navigate` or similar tool bubbles
