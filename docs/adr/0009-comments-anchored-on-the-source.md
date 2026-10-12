# ADR-0009: Comments anchored on the Markdown source; Clarify and Resolve as batched turns

- Status: accepted (M1-T02/T03, 2026-10-13)
- Deciders: project owner (what the feature does), implementation (how)

## Context

The owner's most important requirement (ADR-0008, point 7): every answer and every document of
the agent can be commented by selecting text and pressing a contextual button. **Clarify**
sends all clarification requests together; the agent expands only the commented passages,
never the whole text. **Resolve** sends all change requests (to the code or to the text)
together; the agent edits the files directly and decides itself what to do when requests
conflict, as it does in a terminal.

The M1 brief asks for anchors that survive repeated phrases, Unicode and formatting, that
never attach a comment to a place by guessing, and for focused questions that do not grow the
main conversation.

## Decisions

1. **A passage is a range of the Markdown source**, not of the rendered page. The API counts
   offsets in Unicode code points (what indexing a Python string gives); the browser converts
   from and to UTF-16 in one place (`lib/sourceMap.ts`). With the range are kept the text it
   selects (`quote`) and up to 64 characters before and after it.

   The source is what the agent needs to see (a formula as LaTeX, not as glyphs), what a
   rewritten text can be searched for, and what does not change when the renderer does.

2. **The page carries marks of where each piece comes from.** A rehype step
   (`components/markdown/sourcePositions.ts`) wraps every run of text whose characters map one
   to one to the source in a leaf with its source offsets, and every atom (a formula, inline
   code, a code block, an image, and text the source writes differently from what is shown:
   an escape, an entity, a line of a quote) in a leaf that is taken whole. A selection is
   exact to the character inside plain text and covers an atom whole when it touches it.
   Formulas are rendered after the marks are placed, inside them.

3. **The server never trusts a place.** A comment is created with offsets and the quote, and
   the quote must be exactly what the offsets select in the stored text (422
   `anchor_mismatch` otherwise, with the current version). Without offsets the quote must
   occur exactly once (`quote_ambiguous`, `quote_missing`).

4. **When a text is rewritten every comment is looked for again** (`core/anchors.locate`): a
   quote that occurs once moves there; equal quotes are told apart by the kept context, and
   only if one agrees better than all the others; otherwise the comment is **detached**. A
   detached comment keeps what it said and what it was about, and says that its passage is
   gone. Nothing is attached by guessing. An answer in a conversation is a record and is
   never rewritten, so its comments never move.

5. **Highlights do not change the page.** They are drawn with the CSS Custom Highlight API
   (ranges registered under a name), so what React rendered stays what React rendered and
   overlapping comments need no markup. A browser without that API shows the comments in the
   list without the highlights.

6. **Three kinds of comment:** `clarification` (explain this), `change` (change the code or
   the text), `note` (for people; the agent never sees it). States: `open`, `pending` (with
   the agent), `answered`, `resolved`, `declined`, `dismissed`.

7. **Clarify** is one read-only turn for every open clarification of one text. The answer is
   structured (`{answers: [{id, markdown}]}`); each answer is kept on its comment and shown
   right after the block of its passage, and in the list. The text is not touched: its version
   and content are the same before and after.

8. **Resolve** is one turn for every open change request of one text, in `edit` mode by
   default (files are edited, commands refused) or `full` on request, never read-only. The
   agent edits the project's files directly (the owner's decision; ADR-0008). The answer is
   `{results: [{id, decision: applied | declined, summary}], document}`: a request the agent
   declines says why, and `document` is the complete revised text when the text had to
   change. A revised text becomes the next version of the document, current with the files it
   was written from and the files the turn read or changed, as they are when the turn ends;
   then decision 4 applies to every comment of that document.

9. **Neither grows a conversation.** Each text has a session of its own for Clarify and one for
   Resolve (`agent_sessions.target_type`, `target_id`, `target_version`). The first turn
   shows the agent the text; later requests about the same version continue that session
   with only the new requests, so the text is not sent again. A rewritten text starts a new
   session. The agent is not shown the conversation that produced the text: it gets the text
   (and, for an answer, the question it answered) and reads the code it needs.

10. **A comment a turn did not answer is open again** with the reason: the turn failed, was
    stopped, was interrupted, or left that request out.

## Consequences

- Forking the provider session that wrote the text (so that the agent would remember what it
  read) was not chosen: the fork would send the whole earlier context again on every request,
  and would depend on the provider's own session files. A session per text with the text in
  it costs the system prompt once and little afterwards.
- A selection inside a code block or a formula comments the whole block. Comments on one line
  of code inside a block are not possible yet.
- A detached comment cannot be attached to a new passage by hand; it can be withdrawn and
  written again.
- An answered clarification stays where its passage is. If the passage is rewritten, the
  clarification is detached with it and remains in the list.
- Resolve changes files without a step in between. What changed is listed on the turn (files
  written) and is in Git; nothing reverts it.
- Earlier versions of a rewritten document are not kept (see architecture.md, known limits).
