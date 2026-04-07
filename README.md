# hermes-imessage

A set of patches and a Hermes agent skill that make [Hermes Agent](https://github.com/NousResearch/hermes-agent) feel native on iMessage via [BlueBubbles](https://bluebubbles.app).

Out of the box, Hermes treats iMessage like any other platform -- long messages, tool-use progress spam, no typing indicators. These patches fix that, making conversations feel like texting a friend, not querying a terminal.

> [!NOTE]  
> I've pushed the core of this thing upstream here: https://github.com/NousResearch/hermes-agent/pull/5869
> Though, this version has a few more opinionated UX decisions

## What it does

**Message delivery**
- Splits responses on paragraph breaks so each thought arrives as its own iMessage bubble
- Reduces max chunk size from 4,000 to 800 characters for natural text-sized bubbles
- Strips `(1/3)` pagination indicators -- iMessage bubbles flow naturally without them

**Acknowledgments**
- Sends a quick, contextual acknowledgment (via a fast LLM call) before the main model starts thinking, so you're not staring at silence for 30+ seconds
- Falls back to "One sec..." if the LLM call fails

**Tool-use progress**
- Suppresses per-tool progress messages on platforms that don't support message editing (the root cause of the `browser_navigate: "..."` spam)

**System prompt**
- Injects iMessage-specific platform notes telling the model to keep responses short and conversational -- "think texts, not essays"
- Instructs the model to structure longer replies as separate short thoughts separated by blank lines (which the adapter then delivers as individual bubbles)

**Input debouncing**
- Buffers rapid inbound messages (2-second window) before dispatching to the agent
- Prevents iMessage link previews and multi-bubble pastes from triggering duplicate responses

## Installation

### As patches (recommended)

Apply the patches to your local Hermes install:

```bash
cd ~/.hermes/hermes-agent

# Apply all three patches
git apply /path/to/hermes-imessage/patches/bluebubbles-ux.patch
git apply /path/to/hermes-imessage/patches/gateway-ack-and-progress.patch
git apply /path/to/hermes-imessage/patches/session-platform-notes.patch

# Restart the gateway
hermes gateway restart
```

To undo:

```bash
cd ~/.hermes/hermes-agent
git checkout -- gateway/platforms/bluebubbles.py gateway/run.py gateway/session.py
hermes gateway restart
```

### As a Hermes skill

Copy the skill into your skills directory:

```bash
cp -r /path/to/hermes-imessage/skill/imessage-ux ~/.hermes/skills/imessage-ux
```

The skill provides guidance to the agent on how to behave when responding via iMessage, but the full experience requires the patches above.

## Configuration

The acknowledgment message uses your configured LLM provider via Hermes' `call_llm` helper. By default it targets `gpt-5.4-mini` -- edit the model name in `gateway/run.py` if you use a different provider.

The debounce window is 2 seconds. Adjust `self._DEBOUNCE_SECS` in `bluebubbles.py` if needed.

## Files

```
patches/
  bluebubbles-ux.patch           # Adapter: chunking, paragraph splitting, debounce
  gateway-ack-and-progress.patch # Gateway: contextual ack, suppress tool progress
  session-platform-notes.patch   # Session: iMessage-specific system prompt
skill/
  imessage-ux/
    SKILL.md                     # Hermes agent skill
```

## Requirements

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) with BlueBubbles adapter
- [BlueBubbles](https://bluebubbles.app) server running on a Mac
- A configured LLM provider (for acknowledgment messages)

## License

MIT
