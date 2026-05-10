from __future__ import annotations

from marktex.schema.registry import CallSpec, ContextSpec, SchemaRegistry, ShadeSpec

LAYOUT_VALUE_SHADES = {
    "A4": ShadeSpec("A4", lowerer="paper_preset", payload={"paper": "a4paper"}),
    "A5": ShadeSpec("A5", lowerer="paper_preset", payload={"paper": "a5paper"}),
    "Letter": ShadeSpec("Letter", lowerer="paper_preset", payload={"paper": "letterpaper"}),
    "landscape": ShadeSpec(
        "landscape",
        lowerer="orientation",
        payload={"orientation": "landscape"},
    ),
    "portrait": ShadeSpec("portrait", lowerer="orientation", payload={"orientation": "portrait"}),
}

TEXT_STYLE_SHADES = {
    "bold": ShadeSpec("bold", lowerer="text_style", payload={"weight": "bold"}),
    "italic": ShadeSpec("italic", lowerer="text_style", payload={"style": "italic"}),
}

IMAGE_VALUE_SHADES = {
    "contain": ShadeSpec("contain", lowerer="fit", payload={"fit": "contain"}),
    "cover": ShadeSpec("cover", lowerer="fit", payload={"fit": "cover"}),
}


def builtin_registry() -> SchemaRegistry:
    """Return a fresh built-in schema registry.

    Shorthand/no-arg behavior lives in data constants above. Adding A-series
    papers or style shorthands should change those constants, not the parser.
    """

    return SchemaRegistry(
        {
            "document": ContextSpec(
                "document",
                calls={
                    "layout": CallSpec("layout", "document_patch", invokable=True),
                    "margin": CallSpec("margin", "document_patch", invokable=True),
                    "bib": CallSpec("bib", "resource_set", invokable=True),
                    "bib+": CallSpec("bib+", "resource_add", invokable=True),
                    "bib-": CallSpec("bib-", "resource_remove", invokable=True),
                    "bibstyle": CallSpec("bibstyle", "document_patch", invokable=True),
                    "citestyle": CallSpec("citestyle", "document_patch", invokable=True),
                },
            ),
            "layout.value": ContextSpec("layout.value", shade=LAYOUT_VALUE_SHADES),
            "inline": ContextSpec("inline", shade=TEXT_STYLE_SHADES),
            "image.value": ContextSpec("image.value", shade=IMAGE_VALUE_SHADES),
            "scope": ContextSpec("scope"),
            "reference": ContextSpec(
                "reference",
                calls={"cite": CallSpec("cite", "citation")},
            ),
            "table-column": ContextSpec("table-column"),
        }
    )
