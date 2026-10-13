# ADR-0011: The pipeline: one text, drawn as a board

- Status: accepted (2026-10-13)
- Decider: project owner (the page and how it behaves), implementation (how)

## Context

The owner asked for a **Pipeline** page: a description of the program in the style of a
whiteboard such as Miro, in which every box also holds the description of that part of the
software, and in which text can be selected to ask for changes or clarifications, as in the
other pages.

This is also the form requirement 3 of ADR-0008 takes ("what happens during execution, without
adding code to the source", ticket M1-T06): the agent reads the code and says what one run
does, part by part. It is a description written from the code. It is not the record of one
run that was observed; that is what the Run Monitor shows.

Two things had to be reconciled. A board is a structure: boxes, arrows, places. A comment
(ADR-0009) is a range of a text: start and end in the Markdown source, the quote and its
context, looked for again when the text is rewritten. Making every box a text of its own would
have given every box its own list of comments and its own Clarify and Resolve, where the owner
asked for all requests to be sent together; and a change that splits a box or adds an arrow
would have had no text to be made on.

## Decisions

1. **A pipeline is a document** of kind `pipeline`, one per project, asked for by a button and
   written by a read-only turn of the task `pipeline`, with a schema for the answer: a title,
   a summary, boxes (`id`, `title`, `kind`: input, process, output or external, `description`
   in Markdown, `files`, `repeats`) and arrows (`from`, `to`, `label`: what passes). The task
   takes the place of `execution_description` in the policy, which no feature ever used
   (revision `0011` renames it where it was saved); until a policy is saved it runs on Sonnet
   with medium effort.

2. **One text, and a structure over it.** From the answer NumericOS puts together one
   Markdown text (`agents/pipeline.build`): the title, the summary, then one section per box,
   its title as a level-2 heading and its description under it. The structure kept beside the
   text (`documents.pipeline`) names, for every box, the range of the text that is its own,
   with its kind, files and what repeats, and lists the arrows. **Comments are attached to the
   text exactly as for any other document**: nothing of ADR-0009 changes, on the server or in
   the anchors. The page draws every box from its range of the text, so a selection inside a
   box is a range of the one text.

3. **The agent gives no coordinates.** Where a box goes is decided by the page: a layered
   layout from left to right in the order of a run, computed from the measured size of the
   boxes. An arrow that names a box that is not there is left out and counted; a box that
   points at itself is said to repeat, on the box.

4. **Clarify is unchanged; Resolve revises boxes and arrows.** The agent is shown the text
   and, after it, the boxes and arrows in words (`pipeline.outline`), which the text alone does
   not say. A clarification is shown inside the box of its passage. A Resolve turn on a
   pipeline is asked for the complete revised pipeline as boxes and arrows (`pipeline` in its
   answer, each box it keeps under the id it has), not for Markdown; the text is put together
   again from them, becomes the next version, and every comment is looked for again in it.

5. **Staleness reaches the box.** The sources of a pipeline are the files the turn read and
   the files its boxes name, with the content hash each had (the files named in the answer are
   hashed when the turn ends, between the transactions, like the files it read). The page
   marks the boxes that name a file that changed since.

6. **The page is a board** (`@xyflow/react` for the surface, `@dagrejs/dagre` for the
   layout; the root `AGENTS.md` allows React Flow "only when needed", and a surface that is
   moved and zoomed, with boxes that are dragged and arrows that follow them, is that need).
   Boxes are coloured by kind and moved by their bar; everything under the bar is text that is
   selected and commented. A selection must lie in one part (a box, or the summary). The list
   of comments, with Clarify and Resolve for the whole board, is beside the board where the
   page is wide, and opens with the first comment. The arrows are also given as a list in
   words.

7. **Where the researcher put the boxes is remembered by the browser**, per pipeline and
   version, not by the API: it is how one person looks at the board, not a fact about the
   project, and it would otherwise be a ledger event per drag. A pipeline that was written
   again is laid out afresh; "Tidy up" forgets the places and lays it out again.

8. **Formulas that arrive inside JSON are repaired, narrowly.** Tried with the real agent,
   an answer had the backslashes of LaTeX doubled in some of its strings (`$\\alpha$`), which
   a renderer takes for a line break and a word. `core/formulas.repair_formulas` undoes that
   only inside `$...$` and `$$...$$`, only outside code, and only where every backslash of the
   formula is doubled and a pair stands before a letter. It is applied to every Markdown that
   arrives in a structured answer (boxes, file descriptions, clarifications, the notes of a
   plan); the answer of the turn is recorded as it was given.

## Tried with the real agent

On 2026-10-13, Claude Code 2.1.296 with Haiku and low effort, on a copy of
`examples/heat2d-python`: the pipeline prompt with its schema gave 10 boxes and 10 arrows,
files as paths of the project, three boxes that repeat and one arrow back that closes the
time loop, descriptions of 52 to 80 words (list-price equivalent 0.012 USD). A Resolve turn
on that pipeline, in `edit` mode, with the schema whose `pipeline` is an object or null, gave
its decision and the complete pipeline again, with the same ids in the same order and the one
box changed that the request was about; no file of the copy was touched.

## Consequences

- Revision `0011`: `documents.pipeline` (JSON), the kind `pipeline`, the task renamed. The
  database is copied aside before it is migrated, as for every revision.
- Two runtime dependencies of the GUI: `@xyflow/react` and `@dagrejs/dagre` (both MIT).
- The label of an arrow is not text of the pipeline: it cannot be commented by itself. A
  comment on either box can ask for it to change, and Resolve gives the arrows again.
- The places of the boxes are not shared between browsers and are lost with the browser's
  storage.
- In Chromium, a drag that starts at a fractional pixel position over scaled content does
  not always extend the selection (seen with synthetic pointer positions; a mouse gives whole
  pixels at the default page zoom). The selection is the browser's own; nothing emulates it.
- As for every document, an earlier version of a pipeline is not kept, and nothing is drawn
  again by itself when the code changes: the page says what changed and offers the button.
