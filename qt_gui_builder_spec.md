# PaperLoom — a Qt visual GUI builder

**Project specification.**

PaperLoom is a desktop GUI builder for Qt designed around direct manipulation. Users start with a blank canvas containing a real window, search a component library, drag components onto the canvas, resize and customize them directly, and generate a working Qt application from the visual design.

PaperLoom targets both beginners who want to build a native Qt application without first learning the entire toolkit and experienced developers who want a fast visual editor with access to precise properties and raw code when needed.

The guiding principle is simple:

> **The bar is MS Paint.**

Pick a tool, drop it, drag it, change what you can see, and keep moving. Power-user functionality exists, but it should not dominate the default interface.

---

# 1. Design philosophy

## 1.1 Compact vs. cramped

"Compact" and "cramped" are different.

PaperLoom should avoid permanently displaying every possible panel simply because the application has them. Qt Designer's Object Inspector, Property Editor, and Resource Browser are useful, but they should not consume screen space the instant the application opens.

The goal is:

> **Most advanced functionality should be something you open, not something you're handed.**

Density is acceptable. Forced density is not.

---

## 1.2 Direct manipulation is the default

The things users change constantly should be editable directly on the canvas:

- Position
- Size
- Text
- Color
- Corner radius
- Opacity
- Other common visual properties

A selected widget receives resize handles directly on the canvas.

A small contextual editing surface exposes its most important properties.

Right-clicking provides common actions such as:

- Delete
- Duplicate
- Copy
- Paste
- Common property editing
- Arrange
- Size
- Animation
- Component-specific actions

The complete property system still exists for precision work. It is simply not permanently occupying the interface.

---

# 2. PaperDesign visual language

PaperLoom's own interface follows the **PaperDesign** design system.

The relevant principles are:

- 8px base unit
- 12-column desktop grid
- Consistent spacing and alignment
- Panels that push content rather than covering it
- One muted accent color
- Accent color reserved primarily for actions and active/selected states
- Flat tree-view rows
- Minimal unnecessary decoration
- Short, purposeful motion
- Lucide icons throughout

The canvas itself uses the PaperDesign 8px grid by default.

### Motion

Motion should communicate state rather than decorate the interface.

- 100ms for immediate state changes
- 180ms for dropdowns and tab switches
- 260ms for large panels moving significant distances

Selection outlines should appear immediately rather than fading in.

### Icons

Lucide is the standard icon family for PaperLoom's own interface and the default icon source offered to users.

---

# 3. Editor theme and application theme

PaperLoom distinguishes between two completely separate themes.

## 3.1 Editor theme

The **editor theme** controls PaperLoom itself:

- Sidebar
- Canvas chrome
- Toolbars
- Panels
- Menus
- Popovers
- Status areas
- Other PaperLoom UI

PaperLoom ships with light and dark editor themes.

The editor theme can be switched through:

- Sun/moon toolbar control
- `View > Toggle PaperLoom Light/Dark`
- `Ctrl+Shift+D`

Every editor surface must use the same theme token system so that light and dark themes maintain correct contrast across the entire application.

---

## 3.2 Application theme

The **application theme** controls the application being designed.

It is independent of the editor theme.

PaperLoom provides light and dark application palettes, with components using semantic style roles rather than hardcoded colors.

For example:

```json
{
  "style_role": "primary"
}
