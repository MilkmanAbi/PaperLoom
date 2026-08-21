# PaperLoom App License

**Status: DRAFT / placeholder.** This is a crude first pass, written to
exist and be filled in gradually, not a finished legal document. Nothing
in this file has been reviewed by a lawyer. Where it disagrees with
[GPLv3-PaperLoom.md](GPLv3-PaperLoom.md) (the actual license PaperLoom's
source is released under), the GPLv3 file is what governs the code -
this document is meant to explain the project in plain language
alongside it, not replace it.

---

## What PaperLoom is

PaperLoom is a visual UI/UX builder for Qt. It generates real PySide6
(Python) or C++/Qt project code from a design you build on a canvas - the
canvas, the component library, and the generated code are all meant to
stay in sync, so what you see while designing is what you get when you
run it.

It was created by Abi (MilkmanAbi) as a friendlier front end to Qt
Designer's own feature set - same power, a gentler learning curve.

## The nature of the project

PaperLoom is free and open-source software, intended to stay that way -
see [GPLv3-PaperLoom.md](GPLv3-PaperLoom.md) for the actual licensing
notice and terms. It's an actively developed personal/independent
project, not a commercial product backed by a company; expect it to
change shape as it grows.

## What it's built on

*(fill in real version numbers and links as they're pinned down)*

- **Python** - the language PaperLoom itself is written in.
- **PySide6 (Qt for Python)** - the Qt bindings PaperLoom uses to build
  its own UI, and one of the two code-generation targets (the other
  being C++/Qt). PySide6/Qt for Python is distributed under the GNU
  Lesser General Public License (LGPL) by the Qt Project/The Qt
  Company - a separate license from PaperLoom's own GPL-3.0, covering
  Qt itself rather than PaperLoom's original code. Anyone shipping an
  app built with PaperLoom should check Qt's own current licensing
  terms for their situation.
- **Qt / Qt for Python component set** - the widget library PaperLoom's
  canvas, component palette, and codegen templates are all built
  against.
- Other libraries PaperLoom depends on at runtime or build time belong
  in this list too, each with its own license noted, as they're
  confirmed - not written up yet.

## What error/crash data collection might actually do

Today: **nothing is collected.** PaperLoom does not send anything,
anywhere, by default.

Settings > Data and Privacy has a "Collect error data and crash
reports" toggle. As of this writing, turning it on does exactly one
thing: when PaperLoom hits an unhandled error, it writes a report (what
went wrong, a traceback, basic platform/version info - see
`core/error_manager.py`) to a JSON file on **your own machine**, under
your local PaperLoom settings folder. Nothing is uploaded or
transmitted anywhere. There is currently no server, account, or service
on the other end of this - the toggle exists so the plumbing is there
ahead of a real reporting system.

The plan is to build this out into something much more capable over
time - project name for that future system: **LilyKnight** (a proper
crash/error logging, debug, and app-tracing tool). When that exists,
this section gets rewritten to say plainly and specifically what it
collects, whether/how it's transmitted, how long it's kept, and how to
opt out - before that version ships, not after.

## Third-party assets

PaperLoom's own logo and mascot (LilyKnight) are original assets made
for this project - see `paperloom/resources/branding/`. Anything else
bundled with PaperLoom (icons, fonts, sample content) that isn't
original to the project should be listed here with its own license as
it's confirmed.

---

*This document will be expanded and corrected over time. If something
here looks wrong or incomplete, that's expected for a draft - it hasn't
been filled out yet, not that it's been checked and is final.*
