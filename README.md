<div align="center"><img src=logo.svg width=45% /></div>

# MarkTeX

MarkTeX is a refined markup language inspired by Markdown. We've refined Markdown's lack of paper layout options, extended its existing syntax, and combined it with LaTeX to make it more suitable for rich text content. Particularly, this project optimizes the experience of writing academic documents.

# Basic Syntax

MarkTeX is based on Markdown, so all standard Markdown syntax is supported. MarkTeX extends this with a powerful, structural logic called **MOS (MarkTeX Object Syntax)**.

The extended syntax follows these five core patterns:

- `!# [MOS]` for modifying **intrinsic state variables**.
- `!@ [MOS]` for opening a scoped style (e.g., western/eastern fonts).
- `!!@ [scope]` for ending a scoped style.
- `!$ [Python expression]` for defining custom variables and logic.
- `[]([MOS])` for in-text formatting (extended from Markdown's hyperlink syntax).
- `[^ [MOS]]` for academic references (extended from Markdown's footnote syntax).
- `[$ [Python expression]]` for evaluating variables in text.

---

## MarkTeX Object Syntax (MOS)

MOS is the "brain" of MarkTeX. It allows you to describe complex layouts and styles using simple, intuitive punctuation. Think of it as **"Separator Gravity"**:

1.  **`:` (Nesting)**: Goes one level deeper. (e.g., `margin: top: 10`)
2.  **`,` (Sub-separator)**: Separates items **within** the same level. (e.g., `top: 10, bottom: 10`)
3.  **`;` (Top-separator)**: Breaks back to the **top level** of the command. (e.g., `layout: A4; margin: 10`)
4.  **`()` (Grouping)**: Explicitly groups a block of MOS to avoid ambiguity in deep nesting.
5.  **Tags**: Values without a colon (like `bold`, `12pt`) are shorthand "tags".

---

## Document & Page Level Settings (`!#`)

In MarkTeX, the document state is managed by a set of **Intrinsic Variables**. While the `!#` command uses lowercase keys for ease of typing, it essentially modifies the corresponding internal state.

All settings are **sticky**: they apply from the page they are defined on until the state is overwritten.

### Paper Layout & Margins
```marktex
!# layout: A4, landscape; margin: 10.5
-- Equivalent to setting global state for layout and margin.

!# margin: top: 20
-- Only the 'top' sub-setting is overwritten.
```

### Column Settings
```marktex
!# column: count: 2, gap: 5
-- Two-column layout starts here.

... content ...

!# column: count: 1
-- Returns to single-column layout.
```

### Header & Footer
Headers and footers are strings that can evaluate intrinsic variables (referenced in **UPPERCASE**) in real-time.
```marktex
!# header: left: "MarkTeX Draft", right: "[$ PAGE.N ] / [$ PAGE.MAX ]"
!# footer: center: "Still [$ PAGE.MAX - PAGE.N ] pages to go"
```

---

## Scoped Styles (`!@` & `!!@`)

Scoped styles apply formatting or layout changes to specific text types or regions. The command `!@` is followed by a MOS object with lowercase keys.

### Built-in Scopes
- `w` (western): Western characters.
- `e` (eastern): CJK/Full-width characters.
- `l` (link): Hyperlinks.
- `h1` - `h6`: Headings.
- **Custom Scopes**: Use `!@ (props)` to create a generic block scope.

### Usage
```marktex
!@ w: font: "Times New Roman", 12pt; e: font: "SimSun", 12pt

This mixed text (中西文混排) uses Times and SimSun automatically.

!!@ w
Now western text returns to default, but eastern text is still SimSun.
!!@ e
```

### Localized Layouts (Columns in Scopes)
You can modify the `column` state within a scope:

```marktex
!@ column: count: 2, gap: 5

This specific block of text will be rendered in two columns. 
Once the scope is closed, the layout reverts to the previous global state.

!!@ column
```

---

## In-text Formatting

### Inline Styles `[]()`
The classic Markdown link syntax is now a style powerhouse:
```marktex
[This is blue and bold](color: blue, bold, 14pt)
[Nested styles [look like this](red)](font: "Arial")
```

### Evaluation `[$ ]`
Insert the result of any Python-style expression using intrinsic variables in **UPPERCASE**:
`Today is [$ TIME.strftime("%Y-%m-%d") ].`
`The deadline is in [$ 24 - TIME.hour ] hours.`

---

## Academic References (`[^]`)

MarkTeX unifies bibliography management into the `[^]` pattern.

### Defining References (BibTeX)
```marktex
[^ @article{Nobody06, 
     author: "Nobody Jr", 
     title: "My Article", 
     year: "2006"} ]
```

### State Manipulation
Intrinsic variables like `BIB` are **Smart Objects**. They support direct assignment and overloaded operators, making it easy to manage collections:

```marktex
!# bib: "main.bib"
-- Set initial bib file.

!# bib: [$ BIB + "additional.bib" ]
-- Smart Objects support direct addition of single strings or lists.

!# bib: [$ BIB - "old.bib" ]
-- Removing a file is just as intuitive.
```

### Citing
```marktex
As shown in [^ Nobody06], the theory holds.
[^ id: Nobody06; pages: 12-15 ] -- Citation with specific pages.
```

---

## Appendix: Intrinsic Variables Reference

In MarkTeX, the document state is a collection of **Intrinsic Variables**. Use them in **UPPERCASE** within `[$ ]` or `!$ ` expressions. When using `!#`, the corresponding lowercase keys are used.

| Variable | Sub-properties / Tags | Description |
| :--- | :--- | :--- |
| **`PAGE`** | `N`, `MAX` | `N`: Current page index; `MAX`: Total page count. |
| **`TIME`** | `year`, `month`, `day`, `hour`, `minute`, `strftime()` | System time object (Python `datetime` style). |
| **`LAYOUT`** | `width`, `height`, `landscape`, `portrait` | Controls paper size and orientation. |
| **`MARGIN`** | `top`, `bottom`, `left`, `right` | Page margins in millimeters. |
| **`COLUMN`** | `count`, `gap` | `count`: Number of columns; `gap`: Gutter width. |
| **`HEADER`** | `left`, `center`, `right`, `justify` | Content of the page header. |
| **`FOOTER`** | `left`, `center`, `right`, `justify` | Content of the page footer. |
| **`BIB`** | (Smart Object) | Bibliography files. Supports `+` and `-` operators. |

---
*MarkTeX - Making academic writing as easy as Markdown, as powerful as LaTeX.*

