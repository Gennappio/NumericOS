# ADR-0012: A document is shared as one HTML file, made by the page

- Status: accepted (2026-10-13)
- Decider: project owner (that documents can be shared), implementation (how; the owner asked
  which of an HTML file and an image is better)

## Context

The owner wants to hand the documents NumericOS holds about a project (the pipeline, for
example) to people who do not run NumericOS, and asked whether to give an HTML file or to
generate an image. NumericOS is local and bound to the loopback interface: there is no address
to send.

What is shared is mostly text with formulas. A pipeline of ten boxes of eighty words each is,
as an image, a strip several thousand pixels wide that cannot be read without zooming, whose
text cannot be searched or copied, and whose formulas are pixels. The theory is a paper of
several pages: as an image it is nothing.

## Decisions

1. **One HTML file per document, which stands on its own.** The text stays text, the
   formulas are typeset, the figures are in the file. It opens in any browser by itself,
   without NumericOS and without a network, and is sent as it is. Printing it from the
   browser gives a PDF, which is what a paper is usually sent as. An image of the board is at
   most a picture for a slide; it is not built.

2. **The file has no script and points nowhere.** Its styles, its fonts and its images are
   in it (`data:` addresses). The Markdown of the agent is rendered as everywhere else: raw
   HTML in it is not rendered and links keep only safe protocols. An image at an address of
   another site that does not allow it to be fetched stays an address; the page says how many
   there were.

3. **The page makes the file** (`components/export`, `lib/export`). The document is rendered
   out of sight with the components that show it in the application, and the markup the
   browser built is read back. Its look is not written a second time: the rules are copied
   from the style sheets of the running page (`pageStyles`), and of the fonts the page
   declares only the ones the browser actually loaded are embedded, each with its file
   (`embeddedFonts`): a text without formulas carries no formula font.

4. **The pipeline is shared as its board, still.** The boxes are rendered once to be
   measured, then placed where the researcher put them (the places the browser remembers for
   that version) or, if nobody did, where the order of a run puts them; the arrows are the
   same lines the live board draws, computed once (`drawBoard`). Nothing can be moved or
   commented in the copy. The arrows are also said in words. A board as wide as its boxes
   would be cut on paper: printed, the copy shows the parts one under the other instead.

5. **A copy says where it comes from**: the project, the version of the document, the model
   that wrote it and when, from how many files, and when the copy was made; and it says so
   when a file the document was written from has changed since, with the files. Whoever
   receives the file has no other way to know.

6. **Not from the API or the command line.** They give the Markdown of a document
   (`numericos doc theory`, `numericos doc pipeline`), which is also kept as files in the
   NumericOS folder. A second renderer on the server (Markdown, formulas, the layout of a
   board, which needs the measure of its boxes) would have to be kept equal to the first by
   hand.

## Consequences

- A file carries the rules of the whole application (about 100 kB) and the fonts in use: a
  pipeline is 300 to 400 kB before its own text and figures.
- Comments and clarifications are not in the copy, and neither are the descriptions of the
  files or the plan, which have no page of their own to be shared from yet.
- The copy is what the document was when the button was pressed. Nothing keeps it current.
- Reading the page's style sheets and its loaded fonts needs a browser that gives both to
  scripts; all current ones do. Where the fonts are not given, the copy falls back to the
  reader's own fonts, and a board may then be a few pixels off its arrows.
