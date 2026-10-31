# Workspace Assembly Lite v2 candidate

Status: implementation and offline validation only; no v2 Guest or model result
is claimed until the preregistered controls and Pilot complete. This version is
independent of v1.0.2 and does not rescore historical runs.

A moves one public note; B first derives the audience from the existing draft
and appends and saves a short audience line,
then waits for the delivered revision, reads its tag through a GUI, and appends
an attachment line. A's message contains availability and revision only; raw
messages remain untouched and an exact-tag leak is a separate process finding.
Both roles may act concurrently, without a forced collision or model-time GUI
focus arbitration. B prework occurs before A publishes only if the recorded
trajectory shows it; a faster A is not artificially delayed.

The task root `/tmp/wa2` keeps the GUI path short. Both topologies receive the
same public note and draft, prompts and scorer. The optional bridge gives B the
same task-root-relative `views/B/inspection_note-rNNNNNN.txt` interface in both:
only a complete saved revision that passed SHA and 0444 checks appears in
`list_saved_artifacts`. Each older revision remains as a separate file. A's
original output is writable. The model harness does not open a view for B.

The task setup selects the sole incoming file and places B's Writer caret in
an empty final paragraph, identically in both topologies, before either model
starts. No inspection tag is prefilled. The scripted task path contains 14
physical GUI inputs when a hotkey chord and a typed string each count as one:
5 A move inputs, 2 B prework, 3 B open/read and 4 B finish. These are grouped
into 11 pyautogui calls; setup, screenshots, messages, sleeps and the optional
revision probe are counted separately. This is not a model execution limit;
real Guest controls must verify the layout and action counts. A separate
optional control modifies/restores A's note via GUI to validate old/new views;
it is outside the core task path.

Artifact Oracle derives the tag from the scoring-side copy of the public source
note, checks byte-preserving move, preserves the draft's two original lines,
checks B's audience line against the draft and correct filename/tag line, and
accepts narrow equivalent audience expressions. GUI reading, prework chronology and message
leaks require the separately recorded behavioral audit and screenshots.
