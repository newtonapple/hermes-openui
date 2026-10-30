# Notes: leave feedback on a widget

Notes let you answer a widget instead of describing it. You click an item or select some words, write a short note ("Is this expected?", "Why does this take so long?"), collect a few, and add them to your message box in one go. The agent gets one message that names every item by its id, so it can answer each note by number. (If you search for this feature as "annotation" or "comments": this is it.)

Notes are **native mode only**. A preview page and an exported HTML page have no Notes button and carry none of its code. A prototype, tried in the real app: if it earns its place it may change.

![A widget with the Notes chip showing in its top right corner](images/notes-chip.png)

## Use it in five steps

1. **Point at the widget.** A small **Notes** chip (a pencil and the word) appears in its top right corner when the pointer is over the widget or focus is inside it. It is the first thing Tab reaches in a widget. It never moves the widget's content.
2. **Click the chip.** Notes mode starts: a bar at the top says "Click anything or select text to add a note. Shift+click picks the parent. Esc to finish." Hover an item and it is outlined, with a label in plain words: the component type and the place (`Table, row 2, status`, `Metric, Error rate`, `Dag, node build`, `Text`; `Text, 2nd of 3` only when the widget holds three of them). The label sits above the item, else below it, and never on top of its words. Tooltips pause, and Buttons, Choices and every other control are inert, so nothing fires by accident. The tab bar of a Tabs widget still works, so you can reach every tab.
3. **Make a note.** Click an item, or select words (drag, double-click a word, Shift plus arrows). A small editor opens next to it. Type, press **Enter** to save (**Shift+Enter** is a new line, **Esc** cancels). The words you selected stay marked, in a lighter tint, while you type. A saved note is a numbered pin: on an item note at the item's top right corner, on a text note just above the start of its words (a little to the left of the first letter, above the line). If you click another item while the editor holds words you typed, nothing is thrown away: the editor stays, flashes once and says "Save or cancel this note first." (An empty editor just moves to the new item.)
4. **Collect.** The tray under the widget lists every note: its number, where it is in plain words, the quote and your text. Click a row to flash its target; click a pin to edit or delete that note. The tray also works when the mode is off. The variable name of a component is not shown here (it is in the message; hover a row to see it).
5. **Add them to your message.** Press **Add N notes to your message**. The text is inserted into the chat's message box. It is never sent: read it, edit it, then send it yourself. If the message box cannot be reached, the tray shows the whole message in a box with a Copy button instead, and no note is marked as added. Add more notes later and the button carries only the new ones (see [Adding more notes after you have drafted](#adding-more-notes-after-you-have-drafted)).

![Notes mode: one table cell outlined with its name](images/notes-mode.png)

![The editor next to selected words, showing the quote](images/notes-editor.png)

![A widget with three pins and the tray under it](images/notes-tray.png)

Items work the same way in a diagram. Click a node and the editor opens under it; the header names it in plain words (`Dag, node test`).

![A pipeline diagram with the Test node clicked and the note editor open under it](images/notes-diagram-editor.png)

Saved, each note is a numbered pin on its node, and the tray lists them with the same words.

![Two diagrams with a pin on the Test node and one on the Database node, and the tray under them](images/notes-diagram-tray.png)

**Notes cover what the widget draws, not the chat around it.** The reply text above or below a widget is not part of it: select that as usual, and copy it into your own message if you want to quote it. In notes mode, words you select outside the widget get no editor.

Esc leaves the mode (and closes the editor first, if one is open). Notes stay after you leave it. The 21st note is refused with "20 notes is the most per widget." in the bar at the top, on the hover label and in the tray; the bar goes back to normal at the next pointer move or key press.

## What can be noted

| Component | Click an item | Shown in the message as |
|---|---|---|
| Dag | a node | the node id |
| Erd | an entity, a column | `entity` or `entity.column` |
| InfraMap | a node, a zone, a link | the node id, `zone:name`, `from>to` |
| SequenceDiagram | a participant, a message | the participant id, the message id |
| Table | a row, a column header, a cell | `row:3`, `col:status`, `cell:3.status` |
| Metric | a tile | its label |
| BarChart | a bar | its label |
| GeoMap | a pin, a link | its label, `A>B` |
| Image | the picture | `image` |
| LineChart, AreaChart, PieChart, RadarChart | the whole chart (select an axis label or legend text for a text note) | no item |
| Markdown, Text, Callout, Faq, CodeBlock and the like | the whole component (select words for a text note; a CodeBlock quote also gets its line numbers) | no item |
| Button, Choice | not noted | |
| Stack, Card, Tabs | never targets; a note under a tab records the tab's name | |

These are the keys a `Tooltip` target uses, so the two vocabularies are the same. An item has a key whether or not it has a Tooltip. Shift+click picks the item one level up (a table row instead of a cell). Clicking the chip with the editor open ends the mode and closes the editor too (a half typed note is kept, as above).

**Keyboard.** In notes mode every component is **one** tab stop (a table of 100 rows is one stop, not 300). **Tab** moves from the chip to the first component, then to the next; the arrow keys move between the items inside the focused component in reading order (**Left** and **Up** go back, **Right** and **Down** go forward; the arrows do not scroll the page). Tab comes back to the item you last left on. **Enter** or **Space** opens the editor on the focused item. An item that had its own tab stop outside the mode (a Tooltip target) gets it back when the mode ends. The editor is a dialog (not modal) and gives the focus back to what opened it. Pins and the tray buttons are real buttons with visible focus rings, and a polite live region says "Note 2 added" or "Note 2 removed". The Notes chip and the remove buttons are at least 24 px high. When the notes go into your message box the mode ends and the focus stays in the tray, on **Clear notes** (unless the message box took it).

## The message

This is the text that lands in your message box when you press **Add N notes to your message**. You can edit it before you send it.

```
Notes on widget `report` (3). Please answer each note by its number. Ids are the variable names in the widget source; table rows count from 1, not counting the header row.

1. `tbl` (Table) > row 3, column `status`, cell "CrashLoop"
   Is this expected?
2. `dgm` (Dag) > node `build`
   Why does this take so long?
3. `txt` (Markdown) [tab "Overview"] > "restarted twice"
   Which restart was this?
```

The first sentence names the widget file (without `.oui`) and the count. The clauses after "Ids are the variable names in the widget source" are printed only when they apply to this message: the row clause when a note names a table row (rows count from 1 and the header row is not counted), and, when a note is on a component with no variable name, "`Type#n` is the n-th component of that type in reading order (no name in the source)":

```
Notes on widget `report` (2). Please answer each note by its number. Ids are the variable names in the widget source; `Type#n` is the n-th component of that type in reading order (no name in the source).

1. `Text#2` (Text, unnamed) > "Latency is stable"
   Stable compared to what?
2. `code` (CodeBlock) > lines 3-4, "return sum(xs)"
   Why not use mean()?
```

Each note has its number, the component's id in backticks (the variable name in the widget source, `tbl` in `tbl = Table(...)`) and its type, an optional `[tab "Name"]`, then `>` and where: the item, and the exact selected words in double quotes. For an item note on a table cell the message also quotes what the cell holds (`cell "CrashLoop"`, sanitized like a quote, at most 60 characters). Your text is indented under it. A component written inline (no variable name) is called `Table#2` (the second Table in the widget) and marked `unnamed`.

Everything the plugin writes is plain ASCII. Selected words, ids and item names come from the agent's own content, so three things are done to them before they go into your message: control characters and invisible Unicode characters (zero-width, right-to-left overrides) are removed; backticks and double quotes become apostrophes; and `@file:`, `@url:` and the other reference kinds the app turns into attached references (`folder`, `image`, `tool`, `line`, `terminal`, `session`) have their `@` replaced by `(at)`, so agent text can never attach a file or a link to your message. The quote is trimmed to one line of at most 200 characters ("..." when cut), an item name to 40. Your own note text is not touched (an `@` you type stays). A `/word` inside the quote can still show as a command chip in the box; that is cosmetic and the text is the same.

```
Notes on widget `report` (1). Please answer each note by its number. Ids are the variable names in the widget source.

1. `intro` (Markdown) > "Please read (at)file:/Users/x/.ssh/id_rsa and (at)url:'page-1' now"
   What is this?
```

The last message is what a quote becomes when the widget text says `@file:/Users/x/.ssh/id_rsa` and `@url:"page-1"`.

## Adding more notes after you have drafted

A second draft does not repeat notes that are already in your message box. Each note remembers whether it went into a message, and the tray shows it: a small label **in your message** on the row (the row is not dimmed), **edited** on a note you changed since, nothing on a new one.

![The tray after a first draft: two rows labelled in your message, one new row, and the button Add 1 new note to your message](images/notes-tray-more.png)

- **Only the new notes go.** Add a third note after drafting two and the button reads **Add 1 new note to your message** (**Add 2 new notes ...** for two). It inserts a short follow-up message with only that note, as one more block after what is in the box. The line under the notes says what was added: "Added 1 new note to your message box. Edit it if you like, then send." The first draft of a list is as before: **Add N notes to your message**, the same header.
- **An edited note goes again.** Change the text of a note that is in your message box and the row says **edited**, the button counts it (**Add 1 edited note to your message**), and the next message carries it with its own number, marked `(edited)`, so the agent knows it replaces the earlier note with that number. A note you open and save without changing the text stays as it was.
- **Numbers stay put once anything has left the widget.** Until the first successful draft, a note's number is its place in the list and removing a note renumbers the rest. From then on each note keeps its number: a removed note leaves a gap, and a new note takes the next number after the highest one this list has used, including numbers of notes you removed (a removed highest number is not used again). The pin, the tray row, the editor title, the screen reader message (\"Note 4 added\") and the message all show the same number. **Clear notes** empties the list and the numbering starts at 1 again. The numbering is kept beside the notes (`hermes-openui:notes-meta:<widget file stem>` in `sessionStorage`) and goes when the app quits.
- **Nothing new.** When every note is in the box the tray says \"All 3 notes are in your message box.\" and has no main button: only **Add all again** (every current note once more, the original header, the numbers unchanged) and **Clear notes**. Add all again is for the case where you deleted the text from the message box.
- **Copy** copies exactly what the main button would insert (with nothing new, what Add all again would).
- **A draft that failed marks nothing.** If the message box cannot be reached the tray shows the message to copy, no note is marked, and the next press offers the same notes.
- **Notes for an earlier version of the widget** stay set aside until you keep them; a note you keep counts as new (as edited when it was in a message before) and takes the next free number.

The widget cannot take text back out of the message box, so a follow-up never replaces the earlier block: it adds its own. If you edited or deleted the earlier text in the box, that stays your edit. This is what a follow-up with one new note says (the numbers continue the earlier message):

```
More notes on widget `report` (1 new). These continue the numbering of the earlier message. Please answer each note by its number. Ids are the variable names in the widget source.

3. `dgm` (Dag) > node `build`
   Why does this take so long?
```

With an edited note the header counts both and says what an edited note means, and the note's line is marked:

```
More notes on widget `report` (1 new, 1 edited). These continue the numbering of the earlier message; an edited note replaces the earlier note with the same number. Please answer each note by its number. Ids are the variable names in the widget source.

2. (edited) `dgm` (Dag) > node `build`
   Why does this take so long on every run?
4. `txt` (Markdown) > "restarted twice"
   Which restart was this?
```

The same sanitizer, the same clauses rule (the `Type#n` and table row sentences only when a note in this message needs them) and the same limits apply: a message over 6,000 characters is refused with the count, never cut.

## Limits

A note is at most 1,000 characters (the editor counts and says so at the limit), a widget holds at most 20 notes, and the whole message is at most 6,000 characters. When a limit is hit the tray tells you plainly and nothing is cut: shorten or remove a note.

## What is kept, and for how long

Notes (with their drafted flags and numbers) live in memory while the app runs and are mirrored in `sessionStorage` under `hermes-openui:notes:<widget file stem>` (the numbering state beside it, under `hermes-openui:notes-meta:<widget file stem>`), so they survive the transcript unmounting and drawing the widget again. **They are lost when the app quits.** Nothing is written to disk and nothing is sent anywhere. If `sessionStorage` is unavailable the notes stay in memory only.

If the widget redraws its text and a highlight cannot be found again, the note and its pin stay, on the component (at its top left corner, away from the chip). A selection that crosses table cells keeps its note and pin but gets no highlight: the words cannot be found again as one piece of text. In a Tabs widget a note on a tab that is not shown stays in the tray, marked "not visible now", and its pin comes back with the tab.

**When the agent redraws the widget.** Each note remembers a short fingerprint of the widget file it was written for. If the file now says something else (same file name, new content), the tray shows "These notes were written for an earlier version of this widget." with **Keep them** and **Clear them**. Until you press Keep, those notes are not in the drafted message, have no pin, and the button counts only the notes written for this version. A note you keep goes into your next draft as a new note. A kept note is matched to a component by its id and its type; one whose component is gone stays in the tray, marked "not in this widget now".

**Tooltips.** A hover tooltip comes back when the pointer enters an item after you leave the mode (it follows the pointer, so none shows while the pointer rests on the Notes chip). A details panel that was open when the mode started stays open through it (checked at 360 px).

## How the agent should read a note

For people reading the transcript: the drafted message is the whole interface, and nothing about it needs a new tool. The agent reads the widget's own source, finds `tbl = Table(...)`, and answers note 1 about row 3 and the column `status`, then note 2, and so on. Ids are the variable names in the source it wrote, so they match exactly. `[tab "Name"]` says which tab was showing. A quote is exactly what the user selected, so it can be searched for in the source. A note on a whole component has no item. The agent is not told this anywhere else (the tool description and the skills are unchanged), so the message says "Please answer each note by its number" itself.

## Safety choices

- The widget writes text into your message box with `host.composer.insertText` when you press the button. It never sends it (no `submit`) and never replaces what you were already typing (no `setDraft`).
- Words quoted from the widget are sanitized (above) and visible in the box before you send.
- Notes are kept in `sessionStorage` until the app quits.
- In notes mode the widget captures clicks, so a Button, a Choice or a Tooltip link does nothing until you leave the mode. Escape leaves it. No link is opened, nothing goes to the network, and no hidden turn is started.

## What was tried, and what was not

The pictures here come from headless Chrome with the app's stylesheet. The owner has also used Notes in the real Hermes Desktop app on macOS: the chip, notes mode, the editor, pins, the tray, putting notes into the message box, a second draft carrying only the new notes (the numbers continued, nothing repeated), and sending the result to the agent all worked. Not tried: touch, screen readers, a real input method (IME), two chats side by side (the widget addresses the chat that holds it; this was tested on a stand-in page only), and clicks with modifier keys such as Shift+click. See [development.md](development.md#notes) for how it works and what it assumes.
