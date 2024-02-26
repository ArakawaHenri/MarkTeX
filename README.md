<center><span style="font-family: Times New Roman; font-size: 12vw;">Mark</span><span style="font-family: Cambria Math; font-style: italic; font-size: 12vw;">TeX</span></center>

# MarkTeX 

MarkTeX is a refined markup language inspired by Markdown. We've refined Markdown's lack of paper layout options, extended its existing syntax, and combined it with LaTeX to make it more suitable for rich text content. Particularly, this project optimizes the experience of writing academic documents.

# Development Plan:

We plan to use rust to write a parser that converts MarkTeX to LaTeX files, and then use the wasm compiled by rust with the existing JavaScript parser projects that convert tex to html or pdf to achieve the preview function of the webview based editor and the function of exporting pdfs.

# Syntax changed based on markdown (draft) 

## File header settings: 

<!-- ```
!# title: Title of the document
``` -->

### Paper layout Settings:

You can set the standard paper size directly:

```
!# layout: A4, [orientation]
<!-- orientation can be 'portrait' or 'landscape' -->
```

or you can set the paper size manually:

```
!# layout: [width], [height]
```

where width and height are in millimeters.

Additionally, you can set the margins of the document:

```
!# margin: [top], [bottom], [left], [right]
```

where the values are in millimeters as well.

### Column Settings: 

```
!# column: 2, 1
!# column: 2, 1g
!# column: 1: 2, 1
!# column: 1: 2, 1g
```

These four lines of code express the same purpose, setting the first page as a two-column page and using a single-column layout for each subsequent page. \
'g' for "global", which represents the default layout in addition to the other specified pages. \
Numbers without a specified page number are automatically interpreted as the default layout.

```
!# column: 1: 2, 1g, -1: 2
```

Negative numbers can be used to express page numbers counted from the end of the document

### Page header and footer settings: 

```
!# .- Left-aligned footer
!# -.- Center-aligned footer
!# -. Right-aligned footer
!# `- Left-aligned header
!# -`- Center-aligned header
!# -` Right-aligned header
```

#### Automatic page numbering: 

In MarkTeX header and footer settings, you can use &lt;N&gt; (Num) and &lt;M&gt; (Max) to freely set the page numbering.

```
!# -. Page <N> of <M>
```

or

```
!# -. 第 <N> 页，共 <M> 页
```

Additionally, you can use N and M for calculations as long as you like：

```
!# -. Still <M-N> pages to go
```

or

```
!# -. 余 <M-N> 页
```

## Fonts & formatting:

We have extended the markdown language's hyperlink syntax to provide flexible fonts and formatting support:

```
[Text]([tag1]: [value], [tag2]: [value], ...)
```

The current drafted tags include:

```
font: [font name]
size: [font size] (in points)
align: left, center, right, justify
color: [font color] or rgb([r], [g], [b])
bold: true (default) or false
italic: true (default) or false
underline: true (default) or false
strikethrough: true (default) or false
linespacing: [value] (in points)
rowspacing: [value] (in points)
href or link: [link]
```

Particularly, for ease of use, `[number + pt]` and any color name defined by html can also be used directly as a tag without the parameter.

```
[This is a paragraph in 12 point using Times New Roman font.](font: Times New Roman, size: 12)
[This is a paragraph in 12 point using Times New Roman font.](font: Times New Roman, 12pt)
[This is a red-colored paragraph.](color: rgb(255, 0, 0))
[This is a red-colored paragraph.](red)
[This is a MintCream-colored paragraph.](MintCream)
[This is a hyperlink in new syntax.](href: https://www.example.com)
```

A format setting expression can be interpreted as a hyperlink to achieve markdown compatibility only when a bracket contains only one link and no other tags:

```
[This is a hyperlink in markdown syntax.](https://www.example.com)
```

### Scope of formatting:

To minimise the hassle, we introduced the concept of scopes, where a scope is labelled with a '*'. \
We defined the following scope for now:

```
*: All text
*w or *western: Western text
*e or *eastern: Eastern Full-width text (Chinese, Japanese, Korean, ...)
*l or *link: Hyperlink
*h or *heading: Heading
*h1, *h2, *h3, *h4, *h5, *h6: Heading 1-6
```

For example:

```
*(font: Times New Roman, size: 12)
^ This sets the entire document to Times New Roman 12pt.

*w(font: Times New Roman, size: 12)
^ This sets the western text to Times New Roman 12pt.

*e(font: 宋体, size: 12) or *e(font: SimSun, size: 12)
^ This sets the eastern text to SimSun 12pt.

*l(blue, italic, underline)
^ This sets the hyperlink to blue, italic, and underlined.

*h(bold)
^ This sets all headings to bold.
```

Formatting scopes have priority from inside out, front to back, the same as in mathematical calculations. However, the setting of a particular scope only affects the tags it explicitly sets and does not override the setting of other scopes:

```
*w(font: Times New Roman, size: 12)
*e(font: SimSun, size: 12)
*l(blue, italic, underline)
^ This sets the western text to Times New Roman 12pt, the eastern text to SimSun 12pt, and the hyperlink to blue, italic, and underlined.
```

```
*l(blue, italic, underline, size: 13)
*w(font: Times New Roman, size: 12)
*e(font: SimSun, size: 12)
^ Wrong way to set the font, settings for the size of hyperlinks are overridden by later settings for oriental characters and western text. But the settings for the color, italic, and underline of hyperlinks are still valid.
```

```
*w(font: Times New Roman, size: 12)
*e(font: SimSun, size: 12)
*l(blue, italic, underline)

[intext settings have the highest priority.](font: Arial, size: 14)
^ This sets the western text to Times New Roman 12pt, the eastern text to SimSun 12pt, and the hyperlink to blue, italic, and underlined as default. The text in the square brackets is set to Arial 14pt.
```

### Undoing settings for a scope:

To undo settings for a scope, use the following syntax:

```
![scope]
```

For example:

```
*(bold)

Here's something important.

!*

Something regular.
```

Undoing settings for a scope will only only affects the last setting of the scope:

```
*w(font: Times New Roman, size: 12)
*e(font: SimSun, size: 12)
*l(blue, italic, underline)

... some text ...

*(bold)

Here's something important.

!*

Texts here are still in Times New Roman 12pt, SimSun 12pt, and hyperlinks are still blue, italic, and underlined, as undoing settings for a scope only affects the last setting of the scope.
```

Specially, these expressions can be used to undo settings for all scopes:

```
!**
!all
```

## Academic References:

## ... Still Under Construction